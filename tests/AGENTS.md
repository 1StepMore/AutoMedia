# tests/ — 测试 scope

此地何为真：pytest 测试套件；conftest 注册 marker（`e2e` / `redline` / `slow` / `smoke` / `cruel`）。

- 默认 addopts 排除 e2e（pyproject）；E2E 载体 = `pytest tests/test_e2e -m e2e`（Owner D2 认定）。
- 测试数据只用 `tests/fixtures/synth/` 合成件（红线 4）；零生产数据。
- 期望/验收场景的事实源在 `scenarios/`（经 `.agents/expectations/INDEX.md` 指针）——测试代码是期望的执行，不是定义。
