"""
ai.py
-----
Local AI for Prinaka: a chat with a language model served by Ollama
(http://localhost:11434), which may also call a short list of tools (see
ai_tools.py) to act on Prinny.

Everything stays on this PC: nothing is sent to an online service.

- is_running(), installed_models(): ask the Ollama server what is available
- ChatSession: one conversation; the model runs in a background thread and
  the tools that touch the interface run on the GUI thread
"""

import difflib
import json
import threading
import urllib.error
import urllib.request

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OLLAMA_URL         = "http://localhost:11434"
DEFAULT_MODEL      = "qwen3:8b"
KEEP_ALIVE         = "5m"     # Ollama frees the GPU memory after this idle time
REQUEST_TIMEOUT_S  = 180      # the first request also loads the model
CHECK_TIMEOUT_S    = 2
TOOL_TIMEOUT_S     = 10
MAX_TOOL_STEPS     = 4        # tool rounds per message, so a confused model cannot loop
MAX_TURNS          = 10       # past exchanges kept, tool calls included
CONTEXT_TOKENS     = 8192     # Ollama's default window is too short for tools plus history
# appended to every tool result: a small model otherwise answers in character and forgets to say how it went
OUTCOME_HINT = ("\n[Your reply must first say plainly how it went (what was done, or what failed and why), "
                "in the user's language; then at most one short remark in character.]")
SEARCH_TOOL = "web_search"
SIMILAR_REPLY      = 0.72     # a new answer this close to a recent one is written again
REPEAT_CHECK_LAST  = 4        # recent answers compared with the new one

# Sampling that keeps a small model from looping on the same sentences
SAMPLING = {
    "temperature": 0.85, "top_p": 0.9, "top_k": 40,
    "repeat_penalty": 1.15, "repeat_last_n": 256,
    "presence_penalty": 0.6, "frequency_penalty": 0.3,
    "num_ctx": CONTEXT_TOKENS,
}


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


# Tools whose output or arguments are personal (addresses, user and PC names, running programs,
# threats, pages visited, searches). They are used for the answer, then forgotten: nothing of
# them stays in the history sent with the next messages, and the answer that quotes them goes too.
SENSITIVE_TOOLS = ("run_command", "diagnostic", "get_status", "open_website", "open_search", "git_status")
FORGOTTEN       = "(not kept)"


def _forget_sensitive(turn: list) -> list:
    """The messages of one exchange without anything a sensitive tool returned or was given."""
    if not any(m.get("tool_name") in SENSITIVE_TOOLS for m in turn):
        return turn
    kept = []
    for message in turn:
        if message.get("tool_name") in SENSITIVE_TOOLS:
            message = {**message, "content": FORGOTTEN}
        elif message.get("role") == "assistant":
            if message.get("tool_calls"):
                message = {**message, "tool_calls": [
                    {"function": {"name": c["function"]["name"],
                                  "arguments": {} if c["function"]["name"] in SENSITIVE_TOOLS else c["function"].get("arguments")}}
                    for c in message["tool_calls"]]}
            else:
                message = {**message, "content": FORGOTTEN}      # the answer quotes the output
        kept.append(message)
    return kept


class OllamaError(Exception):
    """The server is unreachable or refused the request."""


def _request(path: str, body: dict | None = None, timeout: float = REQUEST_TIMEOUT_S) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        OLLAMA_URL + path, data, {"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.load(e).get("error", "")
        except (ValueError, OSError):
            pass
        raise OllamaError(detail or f"HTTP {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise OllamaError(f"unreachable: {e}") from e


def installed_models() -> list | None:
    """Names of the models Ollama has, or None if the server does not answer."""
    try:
        return [m["name"] for m in _request("/api/tags", timeout=CHECK_TIMEOUT_S).get("models", [])]
    except OllamaError:
        return None


def is_running() -> bool:
    return installed_models() is not None


def chat(model: str, messages: list, tools: list | None = None, temperature: float | None = None) -> dict:
    """One call to /api/chat; returns the assistant message (content, tool_calls)."""
    options = dict(SAMPLING)
    if temperature is not None:
        options["temperature"] = temperature
    body = {
        "model": model, "messages": messages, "stream": False,
        "think": False, "keep_alive": KEEP_ALIVE, "options": options,
    }
    if tools:
        body["tools"] = tools
    return _request("/api/chat", body).get("message", {})


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

class ToolRequest:
    """A tool call waiting for the GUI thread."""

    def __init__(self, name: str, args: dict):
        self.name   = name
        self.args   = args
        self.result = "error: no answer"
        self.done   = threading.Event()


class ChatSession(QObject):
    """
    One conversation with the local model.

    Args:
        tools: Dict name -> ai_tools.Tool the model may call.
        model: Ollama model name.

    Signals:
        reply(str): the final answer.
        failed(str): the server or the model could not answer.
        acted(str, str): a tool was run (its name, and a detail such as the address opened).
    """

    reply  = pyqtSignal(str)
    failed = pyqtSignal(str)
    acted  = pyqtSignal(str, str)
    _gui_tool = pyqtSignal(object)    # worker -> GUI thread

    def __init__(self, tools: dict, model: str = DEFAULT_MODEL, parent=None):
        super().__init__(parent)
        self._tools   = tools
        self.model    = model
        self._turns   = []      # one list of messages per exchange
        self._busy    = False
        self._gui_tool.connect(self._run_gui_tool)

    @property
    def busy(self) -> bool:
        return self._busy

    def clear(self) -> None:
        self._turns = []

    def send(self, text: str, system_prompt: str, repeat_nudge: str = "", allowed: set | None = None,
             search_first: str = "") -> bool:
        """
        Ask the model; False if it is still answering the previous message.

        Args:
            repeat_nudge: Instruction added when the answer repeats an earlier one.
            search_first: Search words to look up on the web before the model answers, for
                questions a small model would otherwise answer from a bad memory.
            allowed: Names of the tools offered; '*' stands for all but the web search;
                None offers every tool; an empty set is plain conversation.
        """
        if self._busy:
            return False
        self._busy = True
        schemas = [tool.schema() for name, tool in self._tools.items()
                   if allowed is None or name in allowed or ("*" in allowed and name != "web_search")]
        threading.Thread(target=self._run, args=(text, system_prompt, schemas, repeat_nudge, search_first),
                         daemon=True).start()
        return True

    def _recent_answers(self) -> list:
        answers = [m["content"] for turn in self._turns for m in turn
                   if m.get("role") == "assistant" and m.get("content")]
        return answers[-REPEAT_CHECK_LAST:]

    def _repeats(self, answer: str) -> bool:
        """True if `answer` is (nearly) one of the last few answers."""
        low = answer.lower()
        return any(difflib.SequenceMatcher(None, low, old.lower()).ratio() >= SIMILAR_REPLY
                   for old in self._recent_answers())

    def _run(self, text: str, system_prompt: str, schemas: list, repeat_nudge: str, search_first: str) -> None:
        answer, error = "", ""
        try:
            # Past tool calls stay in the history: with only the text of earlier
            # answers the model starts claiming actions it never performed.
            messages = [{"role": "system", "content": system_prompt},
                        *(m for past in self._turns for m in past)]
            start = len(messages)
            messages.append({"role": "user", "content": text})
            if search_first and "web_search" in self._tools:
                # shown to the model as if it had asked for the search itself
                query = {"query": search_first}
                messages.append({"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "web_search", "arguments": query}}]})
                messages.append({"role": "tool", "tool_name": "web_search",
                                 "content": self._call_tool("web_search", query)})
            for _ in range(MAX_TOOL_STEPS + 1):
                message = chat(self.model, messages, schemas)
                calls = message.get("tool_calls") or []
                if not calls:
                    answer = (message.get("content") or "").strip()
                    if answer and repeat_nudge and self._repeats(answer):
                        # said before: write it again, more freely, once
                        retry = chat(self.model, [*messages, {"role": "system", "content": repeat_nudge}],
                                     schemas, temperature=1.0)
                        answer = (retry.get("content") or "").strip() or answer
                        repeat_nudge = ""
                    break
                messages.append(message)
                for call in calls:
                    function = call.get("function", {})
                    name = function.get("name", "")
                    messages.append({"role": "tool", "tool_name": name,
                                     "content": self._call_tool(name, function.get("arguments"))})
                    if name == "web_search":
                        schemas = [s for s in schemas if s["function"]["name"] == "web_search"]
            else:
                answer = ""
            messages.append({"role": "assistant", "content": answer})
            self._turns = (self._turns + [_forget_sensitive(messages[start:])])[-MAX_TURNS:]
        except OllamaError as e:
            error = str(e)
        except Exception as e:   # a bad answer from the model must not kill the thread silently
            error = f"{type(e).__name__}: {e}"
        finally:
            self._busy = False
        if error:
            self.failed.emit(error)
        else:
            self.reply.emit(answer)

    def _call_tool(self, name: str, args) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"error: unknown tool '{name}'"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        if not isinstance(args, dict):
            args = {}

        if tool.gui:
            request = ToolRequest(name, args)
            self._gui_tool.emit(request)
            if not request.done.wait(TOOL_TIMEOUT_S):
                return "error: timeout"
            return request.result
        return self._execute(tool, args)

    def _execute(self, tool, args: dict) -> str:
        try:
            result = str(tool.run(args))
        except Exception as e:
            return f"FAILED: {e}" + OUTCOME_HINT
        try:
            detail = tool.describe(args) if tool.describe else ""
        except Exception:
            detail = ""
        if result.startswith(("error", "PARTIAL")):
            outcome = result                         # nothing is reported as done in the chat
        else:
            self.acted.emit(tool.name, detail)
            outcome = result if result.startswith("DONE") else f"DONE: {result}"
        return outcome + OUTCOME_HINT if tool.name != SEARCH_TOOL else outcome

    @pyqtSlot(object)
    def _run_gui_tool(self, request: ToolRequest) -> None:
        request.result = self._execute(self._tools[request.name], request.args)
        request.done.set()
