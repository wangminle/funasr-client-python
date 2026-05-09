#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""simple_funasr_client 子进程退出码回归测试

验证 one_thread 在子进程场景下能够正确传播 worker 执行结果：
1. ws_client 返回 False 时，子进程必须以非零退出码结束
2. ws_client 返回 True 时，子进程应保持成功退出
3. 子进程重新解析到非法 chunk_size 时，必须以非零退出码结束
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

# 添加源码目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, "src", "python-gui-client")
sys.path.insert(0, SRC_DIR)

import simple_funasr_client  # noqa: E402


class TestWorkerExitCodePropagation(unittest.TestCase):
    """测试 worker 结果是否正确映射为子进程退出码"""

    def setUp(self):
        self.original_args = simple_funasr_client.args

    def tearDown(self):
        simple_funasr_client.args = self.original_args

    def test_one_thread_exits_nonzero_when_worker_reports_failure(self):
        """ws_client 返回 False 时，one_thread 必须退出为 1"""
        simple_funasr_client.args = SimpleNamespace(chunk_size=[5, 10, 5])
        fake_loop = mock.Mock()
        fake_loop.run_until_complete.return_value = False
        fake_awaitable = object()

        with mock.patch.object(
            simple_funasr_client,
            "ws_client",
            new=mock.Mock(return_value=fake_awaitable),
        ), \
             mock.patch.object(simple_funasr_client.asyncio, "new_event_loop", return_value=fake_loop), \
             mock.patch.object(simple_funasr_client.asyncio, "set_event_loop"):
            with self.assertRaises(SystemExit) as ctx:
                simple_funasr_client.one_thread(0, 0, 1)

        self.assertEqual(ctx.exception.code, 1)
        fake_loop.run_until_complete.assert_called_once_with(fake_awaitable)
        fake_loop.close.assert_called_once()

    def test_one_thread_keeps_success_exit_when_worker_succeeds(self):
        """ws_client 返回 True 时，one_thread 不应主动抛出 SystemExit"""
        simple_funasr_client.args = SimpleNamespace(chunk_size=[5, 10, 5])
        fake_loop = mock.Mock()
        fake_loop.run_until_complete.return_value = True
        fake_awaitable = object()

        with mock.patch.object(
            simple_funasr_client,
            "ws_client",
            new=mock.Mock(return_value=fake_awaitable),
        ), \
             mock.patch.object(simple_funasr_client.asyncio, "new_event_loop", return_value=fake_loop), \
             mock.patch.object(simple_funasr_client.asyncio, "set_event_loop"):
            simple_funasr_client.one_thread(0, 0, 1)

        fake_loop.run_until_complete.assert_called_once_with(fake_awaitable)
        fake_loop.close.assert_called_once()

    def test_one_thread_exits_nonzero_for_invalid_child_chunk_size(self):
        """子进程重新解析到非法 chunk_size 时，必须退出为 1"""
        simple_funasr_client.args = None
        invalid_args = SimpleNamespace(chunk_size="5,10")

        with mock.patch.object(simple_funasr_client.parser, "parse_args", return_value=invalid_args):
            with self.assertRaises(SystemExit) as ctx:
                simple_funasr_client.one_thread(0, 0, 1)

        self.assertEqual(ctx.exception.code, 1)


def run_tests() -> unittest.result.TestResult:
    """运行测试"""
    print("=" * 70)
    print("simple_funasr_client 子进程退出码回归测试")
    print("=" * 70)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestWorkerExitCodePropagation
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print("=" * 70)
    print(f"运行测试数: {result.testsRun}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print("=" * 70)
    return result


if __name__ == "__main__":
    test_result = run_tests()
    sys.exit(0 if test_result.wasSuccessful() else 1)