#!/usr/bin/env python3
"""FunASR Speech Recognition Skill — 单元测试

测试范围：
1. lib/ 核心模块导入测试
2. funasr_recognize.py 参数解析和格式化测试
3. funasr_probe.py 参数解析测试
4. JSON 输出格式验证
5. 退出码和错误处理测试

注意：本测试不需要实际的 FunASR 服务端，全部为离线测试。
"""

import json
import os
import subprocess
import sys
import unittest

# 项目根目录和 Skill 目录
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SKILL_DIR = os.path.join(PROJECT_ROOT, "skills", "funasr-speech-recognition")
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
LIB_DIR = os.path.join(SCRIPTS_DIR, "lib")

# 将 lib 加入 sys.path 以便测试导入
sys.path.insert(0, LIB_DIR)
sys.path.insert(0, SCRIPTS_DIR)


class TestSkillDirectoryStructure(unittest.TestCase):
    """测试 Skill 目录结构完整性"""

    def test_skill_md_exists(self):
        """SKILL.md 文件必须存在"""
        path = os.path.join(SKILL_DIR, "SKILL.md")
        self.assertTrue(os.path.exists(path), f"SKILL.md 不存在: {path}")

    def test_skill_md_has_frontmatter(self):
        """SKILL.md 必须包含 YAML frontmatter"""
        path = os.path.join(SKILL_DIR, "SKILL.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(content.startswith("---"), "SKILL.md 缺少 YAML frontmatter 开头")
        # 检查有两个 ---（开头和结尾）
        parts = content.split("---")
        self.assertGreaterEqual(len(parts), 3, "SKILL.md frontmatter 格式不完整")

    def test_skill_md_has_name_and_description(self):
        """SKILL.md frontmatter 必须包含 name 和 description"""
        path = os.path.join(SKILL_DIR, "SKILL.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # 提取 frontmatter
        parts = content.split("---")
        frontmatter = parts[1]
        self.assertIn("name:", frontmatter, "frontmatter 缺少 name 字段")
        self.assertIn("description:", frontmatter, "frontmatter 缺少 description 字段")

    def test_recognize_script_exists(self):
        """识别脚本必须存在"""
        path = os.path.join(SCRIPTS_DIR, "funasr_recognize.py")
        self.assertTrue(os.path.exists(path), f"funasr_recognize.py 不存在: {path}")

    def test_probe_script_exists(self):
        """探测脚本必须存在"""
        path = os.path.join(SCRIPTS_DIR, "funasr_probe.py")
        self.assertTrue(os.path.exists(path), f"funasr_probe.py 不存在: {path}")

    def test_lib_modules_exist(self):
        """lib/ 核心模块必须存在"""
        required_files = [
            "__init__.py",
            "protocol_adapter.py",
            "server_probe.py",
            "websocket_compat.py",
        ]
        for fname in required_files:
            path = os.path.join(LIB_DIR, fname)
            self.assertTrue(os.path.exists(path), f"lib/{fname} 不存在: {path}")

    def test_protocol_guide_exists(self):
        """协议参考文档必须存在"""
        path = os.path.join(SKILL_DIR, "references", "protocol_guide.md")
        self.assertTrue(os.path.exists(path), f"protocol_guide.md 不存在: {path}")

    def test_skill_md_under_500_lines(self):
        """SKILL.md 必须少于 500 行"""
        path = os.path.join(SKILL_DIR, "SKILL.md")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertLess(len(lines), 500, f"SKILL.md 行数过多: {len(lines)} 行（应<500）")


class TestLibModuleImport(unittest.TestCase):
    """测试 lib/ 核心模块是否可以独立导入"""

    def test_import_protocol_adapter(self):
        """protocol_adapter 模块导入测试"""
        from protocol_adapter import (
            MessageProfile,
            ParsedResult,
            ProtocolAdapter,
            RecognitionMode,
            ServerType,
            create_adapter,
            create_message_profile,
        )
        # 验证核心类和函数存在
        self.assertIsNotNone(ProtocolAdapter)
        self.assertIsNotNone(ServerType)
        self.assertIsNotNone(RecognitionMode)
        self.assertIsNotNone(MessageProfile)
        self.assertIsNotNone(ParsedResult)
        self.assertIsNotNone(create_adapter)
        self.assertIsNotNone(create_message_profile)

    def test_import_server_probe(self):
        """server_probe 模块导入测试"""
        from server_probe import (
            ProbeLevel,
            ServerCapabilities,
            ServerProbe,
            create_probe_level,
            probe_server_sync,
        )
        self.assertIsNotNone(ProbeLevel)
        self.assertIsNotNone(ServerCapabilities)
        self.assertIsNotNone(ServerProbe)
        self.assertIsNotNone(create_probe_level)
        self.assertIsNotNone(probe_server_sync)

    def test_import_websocket_compat(self):
        """websocket_compat 模块导入测试"""
        from websocket_compat import connect_websocket
        self.assertIsNotNone(connect_websocket)


class TestProtocolAdapterFunctionality(unittest.TestCase):
    """测试协议适配层核心功能"""

    def test_create_adapter_auto(self):
        """创建 auto 类型适配器"""
        from protocol_adapter import ServerType, create_adapter
        adapter = create_adapter("auto")
        self.assertEqual(adapter.server_type, ServerType.AUTO)

    def test_create_adapter_invalid(self):
        """无效类型应降级为 auto"""
        from protocol_adapter import ServerType, create_adapter
        adapter = create_adapter("invalid_type")
        self.assertEqual(adapter.server_type, ServerType.AUTO)

    def test_build_start_message_offline(self):
        """构建离线模式开始消息"""
        from protocol_adapter import (
            MessageProfile,
            ProtocolAdapter,
            RecognitionMode,
            ServerType,
        )
        adapter = ProtocolAdapter(ServerType.AUTO)
        profile = MessageProfile(
            server_type=ServerType.AUTO,
            mode=RecognitionMode.OFFLINE,
            wav_name="test.wav",
        )
        msg = adapter.build_start_message(profile)
        data = json.loads(msg)
        self.assertEqual(data["mode"], "offline")
        self.assertEqual(data["wav_name"], "test.wav")
        self.assertTrue(data["is_speaking"])

    def test_build_end_message(self):
        """构建结束消息"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        msg = adapter.build_end_message()
        data = json.loads(msg)
        self.assertFalse(data["is_speaking"])

    def test_parse_result_offline_complete(self):
        """解析离线结果 — 应标记为 is_complete=True"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        raw = json.dumps({
            "mode": "offline",
            "text": "测试文本",
            "is_final": False,
            "wav_name": "test.wav",
        })
        result = adapter.parse_result(raw)
        self.assertEqual(result.text, "测试文本")
        self.assertTrue(result.is_complete, "offline 模式收到回包应 is_complete=True")
        self.assertFalse(result.is_final)

    def test_parse_result_is_final_true(self):
        """解析结果 — is_final=True 应完成"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        raw = json.dumps({
            "mode": "offline",
            "text": "测试",
            "is_final": True,
        })
        result = adapter.parse_result(raw)
        self.assertTrue(result.is_complete)
        self.assertTrue(result.is_final)

    def test_parse_result_2pass_offline_complete(self):
        """解析 2pass-offline 结果 — 应标记完成"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        raw = json.dumps({
            "mode": "2pass-offline",
            "text": "最终结果",
            "is_final": False,
        })
        result = adapter.parse_result(raw)
        self.assertTrue(result.is_complete)

    def test_parse_result_json_error(self):
        """解析无效 JSON — 应返回错误"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        result = adapter.parse_result("not json")
        self.assertIsNotNone(result.error)
        self.assertFalse(result.is_complete)

    def test_parse_result_empty_text_offline(self):
        """解析空文本离线结果 — 静音场景应正常结束"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        raw = json.dumps({
            "mode": "offline",
            "text": "",
            "is_final": False,
        })
        result = adapter.parse_result(raw)
        self.assertTrue(result.is_complete, "静音场景（空文本）也应 is_complete=True")

    def test_parse_result_stamp_sents_extraction(self):
        """从 stamp_sents 提取文本"""
        from protocol_adapter import ProtocolAdapter
        adapter = ProtocolAdapter()
        raw = json.dumps({
            "mode": "offline",
            "stamp_sents": [
                {"text_seg": "你好", "start": 0, "end": 500},
                {"text_seg": "世界", "start": 500, "end": 1000},
            ],
            "is_final": False,
        })
        result = adapter.parse_result(raw)
        self.assertEqual(result.text, "你好世界")


class TestServerCapabilities(unittest.TestCase):
    """测试服务器能力数据类"""

    def test_to_dict_and_from_dict(self):
        """序列化/反序列化测试"""
        from server_probe import ProbeLevel, ServerCapabilities
        caps = ServerCapabilities(
            reachable=True,
            responsive=True,
            supports_offline=True,
            is_final_semantics="legacy_true",
            inferred_server_type="legacy",
            probe_level=ProbeLevel.OFFLINE_LIGHT,
            probe_notes=["测试"],
        )
        d = caps.to_dict()
        restored = ServerCapabilities.from_dict(d)
        self.assertEqual(restored.reachable, True)
        self.assertEqual(restored.responsive, True)
        self.assertEqual(restored.supports_offline, True)
        self.assertEqual(restored.is_final_semantics, "legacy_true")
        self.assertEqual(restored.inferred_server_type, "legacy")

    def test_display_text_unreachable(self):
        """不可达显示文本"""
        from server_probe import ServerCapabilities
        caps = ServerCapabilities(reachable=False, error="连接超时")
        text = caps.to_display_text()
        self.assertIn("不可连接", text)
        self.assertIn("连接超时", text)

    def test_display_text_reachable(self):
        """可达显示文本"""
        from server_probe import ServerCapabilities
        caps = ServerCapabilities(
            reachable=True,
            responsive=True,
            supports_offline=True,
        )
        text = caps.to_display_text()
        self.assertIn("服务可用", text)
        self.assertIn("离线", text)

    def test_create_probe_level(self):
        """探测级别字符串转换"""
        from server_probe import ProbeLevel, create_probe_level
        self.assertEqual(create_probe_level("connect_only"), ProbeLevel.CONNECT_ONLY)
        self.assertEqual(create_probe_level("offline_light"), ProbeLevel.OFFLINE_LIGHT)
        self.assertEqual(create_probe_level("twopass_full"), ProbeLevel.TWOPASS_FULL)
        # 无效值应降级为默认
        self.assertEqual(create_probe_level("invalid"), ProbeLevel.OFFLINE_LIGHT)


class TestRecognizeScriptCLI(unittest.TestCase):
    """测试识别脚本的 CLI 行为"""

    def test_help_output(self):
        """--help 应正常输出帮助信息"""
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "funasr_recognize.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("FunASR", result.stdout)
        self.assertIn("--host", result.stdout)
        self.assertIn("--audio", result.stdout)

    def test_missing_required_args(self):
        """缺少必需参数应报错"""
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "funasr_recognize.py")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_nonexistent_audio_file(self):
        """不存在的音频文件应返回参数错误"""
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPTS_DIR, "funasr_recognize.py"),
                "--host", "127.0.0.1",
                "--port", "99999",
                "--audio", "/nonexistent/file.wav",
                "--format", "json",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 1, "不存在的文件应返回退出码 1")
        # 验证 JSON 输出格式
        output = json.loads(result.stdout)
        self.assertFalse(output["success"])
        self.assertIn("不存在", output["error"])


class TestProbeScriptCLI(unittest.TestCase):
    """测试探测脚本的 CLI 行为"""

    def test_help_output(self):
        """--help 应正常输出帮助信息"""
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "funasr_probe.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("FunASR", result.stdout)
        self.assertIn("--host", result.stdout)
        self.assertIn("--level", result.stdout)

    def test_unreachable_server(self):
        """不可达服务器应返回 JSON 错误和退出码 2"""
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPTS_DIR, "funasr_probe.py"),
                "--host", "192.0.2.1",   # RFC 5737 文档地址，不可达
                "--port", "99999",
                "--level", "connect_only",
                "--timeout", "2",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 2, "不可达服务器应返回退出码 2")
        output = json.loads(result.stdout)
        self.assertFalse(output["success"])
        self.assertFalse(output["reachable"])


class TestFormatFunctions(unittest.TestCase):
    """测试输出格式化函数"""

    def test_json_result_success(self):
        """JSON 成功结果格式"""
        # 导入格式化函数
        sys.path.insert(0, SCRIPTS_DIR)
        from funasr_recognize import format_json_result
        output = format_json_result(
            success=True,
            text="你好世界",
            mode="offline",
            audio_file="test.wav",
            server="127.0.0.1:10095",
            duration_ms=1234.5,
        )
        data = json.loads(output)
        self.assertTrue(data["success"])
        self.assertEqual(data["text"], "你好世界")
        self.assertEqual(data["mode"], "offline")
        self.assertIsNone(data["error"])

    def test_json_result_error(self):
        """JSON 错误结果格式"""
        sys.path.insert(0, SCRIPTS_DIR)
        from funasr_recognize import format_json_result
        output = format_json_result(
            success=False,
            error="连接被拒绝",
            error_code=2,
        )
        data = json.loads(output)
        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "连接被拒绝")
        self.assertEqual(data["error_code"], 2)

    def test_srt_result_with_stamp_sents(self):
        """SRT 字幕格式 — 有时间戳"""
        sys.path.insert(0, SCRIPTS_DIR)
        from funasr_recognize import format_srt_result
        stamp_sents = [
            {"text_seg": "你好", "start": 0, "end": 1000},
            {"text_seg": "世界", "start": 1000, "end": 2000},
        ]
        output = format_srt_result("你好世界", stamp_sents=stamp_sents)
        self.assertIn("1\n", output)
        self.assertIn("2\n", output)
        self.assertIn("你好", output)
        self.assertIn("世界", output)
        self.assertIn("00:00:00,000", output)
        self.assertIn("00:00:01,000", output)

    def test_srt_result_without_timestamp(self):
        """SRT 字幕格式 — 无时间戳"""
        sys.path.insert(0, SCRIPTS_DIR)
        from funasr_recognize import format_srt_result
        output = format_srt_result("你好世界")
        self.assertIn("1\n", output)
        self.assertIn("你好世界", output)


if __name__ == "__main__":
    # 运行测试
    print("=" * 60)
    print("FunASR Speech Recognition Skill — 单元测试")
    print(f"Skill 目录: {SKILL_DIR}")
    print(f"Python 版本: {sys.version}")
    print("=" * 60)

    unittest.main(verbosity=2)
