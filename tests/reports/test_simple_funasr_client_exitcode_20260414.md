# simple_funasr_client 子进程退出码回归修复测试报告

## 测试信息

- 测试日期: 2026-04-14
- 测试对象: src/python-gui-client/simple_funasr_client.py
- 问题类型: 子进程 worker 失败未正确传播到进程退出码
- 测试环境: Windows + Python 3.12.10

## 问题确认

本次 review 提出的 bug 确认存在。

根因如下：

1. one_thread 调用 ws_client 后直接返回，没有根据返回值设置进程退出码。
2. ws_client 在以下场景会返回 False 而不是直接抛异常：
   - WebSocket 连接失败
   - asyncio.gather 内部任务异常
   - .scp 批处理中的局部失败
3. main 通过各子进程的 exitcode 汇总 overall_success。
4. 因此当 ws_client 返回 False 但子进程自然结束时，父进程会把该子进程视为 exitcode=0，最终误判整体成功。

该问题会影响：

- CLI 自动化调用对失败任务的判断
- GUI 批量识别对部分失败任务的最终状态判断

## 修复内容

已做以下修复：

1. one_thread 在子进程重新解析到非法 chunk_size 时，改为 sys.exit(1)，不再静默 return。
2. one_thread 在执行 ws_client 后检查 overall_success：
   - True: 正常返回，保持成功退出
   - False: 调用 sys.exit(1)，明确传播失败状态
3. 增加事件循环关闭逻辑，避免子进程退出前遗留未关闭 loop。

## 新增测试

新增测试脚本：tests/scripts/test_simple_funasr_client_exitcode_20260414.py

覆盖用例：

1. ws_client 返回 False 时，one_thread 必须抛出 SystemExit(1)
2. ws_client 返回 True 时，one_thread 不应主动退出失败
3. 子进程重解析出非法 chunk_size 时，必须抛出 SystemExit(1)

## 执行结果

### 1. 新增回归测试

执行命令：

```bash
python tests/scripts/test_simple_funasr_client_exitcode_20260414.py
```

执行结果：

- 运行测试数: 3
- 失败: 0
- 错误: 0
- 结论: 通过

### 2. 相关既有测试回归验证

执行命令：

```bash
python tests/scripts/test_v3_subprocess_params.py
```

执行结果：

- 运行测试数: 26
- 失败: 0
- 错误: 0
- 结论: 通过

## 最终结论

本次 review 指出的 bug 真实存在，且已经完成修复。

修复后：

1. worker 侧返回 False 会正确转换为子进程非零退出码。
2. 父进程 main 基于 exitcode 的 overall_success 汇总逻辑恢复正确。
3. 新增回归测试已锁定该行为，避免后续再次退化。