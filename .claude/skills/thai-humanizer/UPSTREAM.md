# Upstream

Vendored from <https://github.com/citelogics-th/thai-humanizer> at commit
`17615e9c1946a5d80d18b2d1091d703257303b3f` (MIT, see `LICENSE`). Upstream
`README.md` is left out because its install steps target `~/.claude/skills`.

## Local changes

- `SKILL.md`: the 15 em dashes (U+2014) are replaced with `:`, `·` or a
  space, so text written under this skill carries no em dashes. Re-apply
  after pulling an upstream update.

`references/` and `LICENSE` are byte-identical to upstream.
