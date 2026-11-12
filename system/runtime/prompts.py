"""Published per-condition collaboration prompts; no hidden Full fallback."""
from common import SYSTEM
DISCUSS=(SYSTEM/"prompts/discuss.md").read_text()
RESPOND=(SYSTEM/"prompts/respond.md").read_text()
SELECT=(SYSTEM/"prompts/select.md").read_text()
