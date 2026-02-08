"""FunASR GUI 客户端（Tkinter 版）。

本模块提供桌面图形界面，集成 FunASR WebSocket 通讯流程与常用操作，
用于加载音频、配置参数与触发识别，并在界面中呈现日志与结果。
"""

import asyncio
import importlib
import json
import logging
import logging.handlers
import os
import queue  # Import the queue module to access queue.Empty
import ssl
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from queue import Queue  # For thread-safe GUI updates from logging handler
from tkinter import filedialog, messagebox, scrolledtext, ttk

# 抑制 macOS 上的 NSOpenPanel 警告
if sys.platform == "darwin":  # macOS
    import warnings

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    # 设置环境变量抑制 Cocoa 警告
    os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"


# --- 语言管理类 ---
class LanguageManager:
    """管理应用程序的多语言支持"""

    def __init__(self):
        """初始化语言管理器。"""
        # 默认语言为中文
        self.current_lang = "zh"

        # 定义所有需要翻译的文本
        self.translations = {
            # 主窗口标题
            "app_title": {"zh": "FunASR GUI 客户端 V2", "en": "FunASR GUI Client V2"},
            # 框架标题
            "server_config_frame": {
                "zh": "服务器连接配置",
                "en": "Server Connection Configuration",
            },
            "file_select_frame": {
                "zh": "文件选择与执行",
                "en": "File Selection and Execution",
            },
            "advanced_options_frame": {"zh": "高级选项", "en": "Advanced Options"},
            "speed_test_frame": {"zh": "速度测试", "en": "Speed Test"},
            "log_frame": {"zh": "运行日志与结果", "en": "Running Logs and Results"},
            "display_frame": {
                "zh": "识别结果与运行日志",
                "en": "Recognition Results and Running Logs",
            },
            "result_tab": {"zh": "识别结果", "en": "Recognition Results"},
            "log_tab": {"zh": "运行日志", "en": "Running Logs"},
            "copy_result": {"zh": "复制结果", "en": "Copy Result"},
            "clear_result": {"zh": "清空结果", "en": "Clear Result"},
            "result_copied": {
                "zh": "识别结果已复制到剪贴板",
                "en": "Recognition result copied to clipboard",
            },
            "no_result_to_copy": {
                "zh": "没有识别结果可复制",
                "en": "No recognition result to copy",
            },
            "result_cleared": {
                "zh": "识别结果已清空",
                "en": "Recognition result cleared",
            },
            # 服务器配置
            "server_ip": {"zh": "服务器 IP:", "en": "Server IP:"},
            "port": {"zh": "端口:", "en": "Port:"},
            "connect_server": {"zh": "连接服务器", "en": "Connect to Server"},
            "not_connected": {"zh": "未连接", "en": "Not Connected"},
            "connected": {"zh": "已连接", "en": "Connected"},
            # 文件选择
            "select_file": {"zh": "选择音/视频文件", "en": "Select Audio/Video File"},
            "start_recognition": {"zh": "开始识别", "en": "Start Recognition"},
            # 高级选项
            "enable_itn": {"zh": "启用 ITN", "en": "Enable ITN"},
            "enable_ssl": {"zh": "启用 SSL", "en": "Enable SSL"},
            "open_log_file": {"zh": "打开日志文件", "en": "Open Log File"},
            "open_results": {"zh": "打开结果目录", "en": "Open Results Directory"},
            # 热词文件
            "hotword_file": {"zh": "热词文件:", "en": "Hotword File:"},
            "select_hotword_file": {"zh": "选择热词", "en": "Select Hotword"},
            "clear_hotword": {"zh": "清除热词", "en": "Clear Hotword"},
            "text_files": {"zh": "文本文件", "en": "Text Files"},
            "select_hotword_dialog_title": {
                "zh": "选择热词文件",
                "en": "Select Hotword File",
            },
            "hotword_selected": {
                "zh": "已选择热词文件",
                "en": "Hotword file selected",
            },
            "hotword_cleared": {
                "zh": "热词文件已清除",
                "en": "Hotword file cleared",
            },
            "hotword_tooltip": {
                "zh": "热词文件格式:\n每行一个热词,支持带权重\n例如: 阿里巴巴 20\n空文件表示不使用热词",
                "en": "Hotword file format:\nOne hotword per line, weight supported\nExample: alibaba 20\nEmpty file means no hotwords",
            },
            # 速度测试
            "speed_test": {"zh": "速度测试", "en": "Speed Test"},
            "not_tested": {"zh": "未测试", "en": "Not Tested"},
            "testing": {"zh": "测试中...", "en": "Testing..."},
            "test_completed": {"zh": "测试完成", "en": "Test Completed"},
            "upload_speed": {"zh": "上传速度:", "en": "Upload Speed:"},
            "transcription_speed": {"zh": "转写速度:", "en": "Transcription Speed:"},
            # 状态栏
            "ready": {"zh": "准备就绪", "en": "Ready"},
            # 识别阶段状态
            "stage_preparing": {"zh": "⚙️ 准备识别任务... {}", "en": "⚙️ Preparing recognition task... {}"},
            "stage_reading_file": {"zh": "📖 读取文件: {}", "en": "📖 Reading file: {}"},
            "stage_connecting": {"zh": "🔌 连接服务器... {}", "en": "🔌 Connecting to server... {}"},
            "stage_uploading": {"zh": "⬆️ 上传音频: {}", "en": "⬆️ Uploading audio: {}"},
            "stage_processing": {"zh": "🔄 服务器处理中{}", "en": "🔄 Server processing{}"},
            "stage_receiving": {"zh": "⬇️ 接收识别结果...", "en": "⬇️ Receiving results..."},
            "stage_completed": {"zh": "✅ 识别完成{}", "en": "✅ Recognition completed{}"},
            # 语言切换按钮
            "switch_to_en": {"zh": "EN", "en": "中文"},
            # 日志消息
            "system_init": {
                "zh": "系统事件: 应用程序初始化",
                "en": "System Event: Application Initialized",
            },
            "debug_log_location": {
                "zh": "调试信息: 日志文件位置: {}",
                "en": "Debug Info: Log file location: {}",
            },
            "debug_current_dir": {
                "zh": "调试信息: 当前工作目录: {}",
                "en": "Debug Info: Current working directory: {}",
            },
            "debug_python_version": {
                "zh": "调试信息: Python版本: {}",
                "en": "Debug Info: Python version: {}",
            },
            "config_loaded": {
                "zh": "系统事件: 配置文件已加载: {}",
                "en": "System Event: Configuration file loaded: {}",
            },
            "config_not_found": {
                "zh": "系统警告: 未找到配置文件，使用默认设置",
                "en": (
                    "System Warning: Configuration file not found, "
                    "using default settings"
                ),
            },
            "config_saved": {
                "zh": "系统事件: 配置已保存到 {}",
                "en": "System Event: Configuration saved to {}",
            },
            "app_closing": {
                "zh": "系统事件: 应用程序关闭",
                "en": "System Event: Application closing",
            },
            "checking_dependencies": {
                "zh": "系统事件: 开始检查必要的依赖",
                "en": "System Event: Checking required dependencies",
            },
            "dependency_installed": {
                "zh": "调试信息: 依赖包 {} 已安装",
                "en": "Debug Info: Dependency {} is installed",
            },
            "dependency_missing": {
                "zh": "系统警告: 依赖包 {} 未安装",
                "en": "System Warning: Dependency {} is not installed",
            },
            "missing_dependencies": {
                "zh": "系统警告: 缺少以下依赖包: {}",
                "en": "System Warning: Missing the following dependencies: {}",
            },
            "auto_install_hint": {
                "zh": "用户提示: 将在连接服务器时尝试自动安装依赖包",
                "en": (
                    "User Hint: Will try to automatically install "
                    "dependencies when connecting to server"
                ),
            },
            "all_dependencies_installed": {
                "zh": "调试信息: 所有必要的依赖都已安装",
                "en": "Debug Info: All required dependencies are installed",
            },
            "installing_dependency": {
                "zh": "系统事件: 开始安装 {}",
                "en": "System Event: Installing {}",
            },
            "install_success": {
                "zh": "系统事件: {} 安装成功",
                "en": "System Event: {} installed successfully",
            },
            "install_failed": {
                "zh": "系统错误: {} 安装失败: {}",
                "en": "System Error: {} installation failed: {}",
            },
            "connecting_server": {
                "zh": "用户操作: 尝试连接服务器: {}:{} (SSL: {})",
                "en": (
                    "User Action: Attempting to connect to server: {}:{} " "(SSL: {})"
                ),
            },
            "connection_params": {
                "zh": "调试信息: 连接参数 - IP: {}, Port: {}, SSL: {}",
                "en": "Debug Info: Connection parameters - IP: {}, Port: {}, SSL: {}",
            },
            "connect_enabled": {"zh": "启用", "en": "enabled"},
            "connect_disabled": {"zh": "禁用", "en": "disabled"},
            "dependency_check_before_connect": {
                "zh": "连接前检测到缺少依赖包: {}",
                "en": "Missing dependencies detected before connection: {}",
            },
            "auto_installing": {
                "zh": "开始自动安装依赖...",
                "en": "Starting automatic dependency installation...",
            },
            "install_failed_cant_connect": {
                "zh": "依赖安装失败，无法测试连接。",
                "en": "Dependency installation failed, cannot test connection.",
            },
            "install_completed_continue": {
                "zh": "依赖安装完成，继续测试连接。",
                "en": (
                    "Dependency installation completed, "
                    "continuing with connection test."
                ),
            },
            "connection_error": {
                "zh": "连接测试时发生错误: {}",
                "en": "Error during connection test: {}",
            },
            "script_not_found_in_current_dir": {
                "zh": (
                    "系统警告: 在当前目录未找到 {}，但在 {} 中找到。"
                    "建议将脚本放在主程序同目录下。"
                ),
                "en": (
                    "System Warning: {} not found in current directory, "
                    "but found in {}. It's recommended to place the script "
                    "in the same directory as the main program."
                ),
            },
            "selecting_file": {
                "zh": "用户操作: 选择音频/视频文件",
                "en": "User Action: Selecting audio/video file",
            },
            "file_selected": {
                "zh": "用户操作: 已选择文件: {}",
                "en": "User Action: File selected: {}",
            },
            "no_file_selected": {
                "zh": "用户操作: 未选择文件",
                "en": "User Action: No file selected",
            },
            "starting_recognition": {
                "zh": "用户操作: 开始识别音频/视频文件: {}",
                "en": "User Action: Starting recognition for audio/video file: {}",
            },
            "please_select_file": {
                "zh": "请先选择音频/视频文件",
                "en": "Please select an audio/video file first",
            },
            "please_connect_server": {
                "zh": "请先连接服务器",
                "en": "Please connect to the server first",
            },
            "recognition_params": {
                "zh": "调试信息: 识别参数 - IP: {}, Port: {}, Audio: {}, ITN: {}",
                "en": (
                    "Debug Info: Recognition parameters - "
                    "IP: {}, Port: {}, Audio: {}, ITN: {}"
                ),
            },
            # 文件选择对话框
            "file_dialog_title": {
                "zh": "选择音频/视频文件",
                "en": "Select Audio/Video File",
            },
            "audio_video_files": {"zh": "音频/视频文件", "en": "Audio/Video Files"},
            "scp_files": {"zh": "SCP文件", "en": "SCP Files"},
            "all_files": {"zh": "所有文件", "en": "All Files"},
            # 错误消息
            "connection_timeout": {
                "zh": "连接超时: 服务器无响应",
                "en": "Connection timeout: Server not responding",
            },
            "communication_timeout": {"zh": "通信超时", "en": "Communication Timeout"},
            "communication_timeout_msg": {
                "zh": "超过 {} 秒未收到服务器响应。",
                "en": "No server response received for {} seconds.",
            },
            "communication_timeout_warning": {
                "zh": (
                    "系统警告: {}秒内未收到服务器响应，"
                    "可能发生通信超时。正在尝试终止进程。"
                ),
                "en": (
                    "System Warning: No server response received for {} "
                    "seconds, possible communication timeout. "
                    "Attempting to terminate process."
                ),
            },
            "transcription_timeout": {"zh": "转写超时", "en": "Transcription Timeout"},
            "transcription_timeout_msg": {
                "zh": "转写时间超过系统等待时长 {} 秒。",
                "en": (
                    "Transcription time exceeded system wait timeout " "of {} seconds."
                ),
            },
            "transcription_timeout_warning": {
                "zh": "系统警告: 转写超过系统等待时长 {}秒，正在终止进程。",
                "en": (
                    "System Warning: Transcription exceeded system wait "
                    "timeout of {} seconds, terminating process."
                ),
            },
            "error_msg": {"zh": "错误：{}", "en": "Error: {}"},
            # 语言切换
            "language_switched": {
                "zh": "系统事件: 已切换到中文界面",
                "en": "System Event: Switched to English interface",
            },
            "speed_test_completed": {
                "zh": "速度测试完成",
                "en": "Speed Test Completed",
            },
            "calculation_failed": {
                "zh": "结果计算失败",
                "en": "Result Calculation Failed",
            },
            "speed_test_calculation_failed": {
                "zh": "速度测试结果计算失败: {}",
                "en": "Speed Test Calculation Failed: {}",
            },
            # 对话框标题和按钮
            "warning_title": {"zh": "警告", "en": "Warning"},
            "error_title": {"zh": "错误", "en": "Error"},
            "info_title": {"zh": "信息", "en": "Information"},
            "speed_test_result_title": {
                "zh": "速度测试结果",
                "en": "Speed Test Results",
            },
            "recognition_error_title": {"zh": "识别错误", "en": "Recognition Error"},
            "startup_error_title": {"zh": "启动错误", "en": "Startup Error"},
            "unexpected_error_title": {"zh": "意外错误", "en": "Unexpected Error"},
            # 速度测试状态和日志
            "test_preparing": {"zh": "测试准备中...", "en": "Preparing test..."},
            "test_progress": {"zh": "测试{}进行中...", "en": "Test {} in progress..."},
            "test_failed_status": {"zh": "测试失败", "en": "Test Failed"},
            "result_calculation_failed_status": {  # 用于状态栏
                "zh": "结果计算失败",
                "en": "Result Calculation Failed",
            },
            "speed_test_event_start": {
                "zh": ("系统事件: 开始速度测试，" "文件1: {} ({}MB), 文件2: {} ({}MB)"),
                "en": (
                    "System Event: Starting speed test. "
                    "File 1: {} ({}MB), File 2: {} ({}MB)"
                ),
            },
            "speed_test_event_testing_file": {
                "zh": "系统事件: 开始测试文件 {}: {}",
                "en": "System Event: Starting test for file {}: {}",
            },
            "speed_test_upload_started": {
                "zh": "速度测试: 文件 {} 上传开始",
                "en": "Speed Test: File {} upload started",
            },
            "speed_test_upload_completed": {
                "zh": "速度测试: 文件 {} 上传完成，耗时: {:.2f}秒",
                "en": "Speed Test: File {} upload completed, duration: {:.2f}s",
            },
            "speed_test_transcription_started": {
                "zh": "速度测试: 文件 {} 转写开始",
                "en": "Speed Test: File {} transcription started",
            },
            "speed_test_transcription_completed": {
                "zh": "速度测试: 文件 {} 转写完成，耗时: {:.2f}秒",
                "en": "Speed Test: File {} transcription completed, duration: {:.2f}s",
            },
            "speed_test_file_completed": {
                "zh": (
                    "速度测试: 文件 {} 测试完成，"
                    "上传耗时: {:.2f}秒，转写耗时: {:.2f}秒"
                ),
                "en": (
                    "Speed Test: File {} test completed. "
                    "Upload: {:.2f}s, Transcription: {:.2f}s"
                ),
            },
            "speed_test_error_missing_timestamps": {
                "zh": "速度测试错误: 未能获取到完整时间点: {}",
                "en": "Speed Test Error: Failed to get complete timestamps: {}",
            },
            "speed_test_error_general": {  # 用于日志
                "zh": "速度测试错误: {}",
                "en": "Speed Test Error: {}",
            },
            "speed_test_results_log": {
                "zh": "速度测试结果: 上传速度 {:.2f} MB/s, 转写速度 {:.2f}x",
                "en": (
                    "Speed Test Results: Upload Speed {:.2f} MB/s, "
                    "Transcription Speed {:.2f}x"
                ),
            },
            # 速度测试结果弹窗
            "speed_test_summary_title": {  # 弹窗内的小标题
                "zh": "测试总结",
                "en": "Test Summary",
            },
            "total_file_size": {"zh": "文件总大小", "en": "Total File Size"},
            "total_upload_time": {"zh": "总上传时间", "en": "Total Upload Time"},
            "average_upload_speed": {
                "zh": "平均上传速度",
                "en": "Average Upload Speed",
            },
            "total_audio_duration": {"zh": "音频总时长", "en": "Total Audio Duration"},
            "total_transcription_time": {
                "zh": "总转写时间",
                "en": "Total Transcription Time",
            },
            "transcription_speed_label": {  # 弹窗内的标签
                "zh": "转写速度",
                "en": "Transcription Speed",
            },
            # 其他状态和对话框
            "status_preparing_speed_test": {
                "zh": "正在准备速度测试...",
                "en": "Preparing speed test...",
            },
            "status_testing_file": {"zh": "正在测试文件: {}", "en": "Testing file: {}"},
            "status_speed_test_failed_with_msg": {
                "zh": "速度测试失败: {}",
                "en": "Speed test failed: {}",
            },
            # "status_speed_test_completed" - Covered by "test_completed" for status bar
            "status_speed_test_calc_failed": {  # status_var用
                "zh": "速度测试结果计算失败: {}",
                "en": "Speed test result calculation failed: {}",
            },
            "user_warn_speed_test_running": {  # status_var用
                "zh": "警告: 速度测试已在进行中",
                "en": "Warning: Speed test already in progress",
            },
            "dialog_speed_test_error_title": {  # messagebox title
                "zh": "测试失败",
                "en": "Test Failed",
            },
            "dialog_speed_test_error_msg": {  # messagebox message
                "zh": "速度测试过程中出错:\\n{}",
                "en": "Error during speed test:\\n{}",
            },
            # "dialog_result_calc_failed_title" - Covered by "calculation_failed"
            # or "speed_test_calculation_failed" for title
            "dialog_result_calc_failed_msg": {  # messagebox message
                "zh": "计算速度测试结果时出错:\\n{}",
                "en": "Error calculating speed test results:\\n{}",
            },
            # 新增
            "test_file_not_found_error": {
                "zh": "测试文件不存在",
                "en": "Test file not found",
            },
            "seconds_unit": {"zh": "秒", "en": "s"},
            # 识别过程中的日志消息
            "server_response": {"zh": "服务器响应", "en": "Server Response"},
            "client_event": {"zh": "客户端事件", "en": "Client Event"},
            "client_debug": {"zh": "客户端调试", "en": "Client Debug"},
            "debug_tag": {"zh": "[调试]", "en": "[DEBUG]"},
            "upload_progress": {"zh": "上传进度", "en": "Upload Progress"},
            "waiting_server": {
                "zh": "等待服务器处理完成",
                "en": "Waiting for server processing to complete",
            },
            "task_success": {
                "zh": "任务成功: 文件 {} 识别完成。",
                "en": "Task Success: File {} recognition completed.",
            },
            "task_failed": {
                "zh": "任务失败: 文件 {} 识别出错。返回码: {}",
                "en": "Task Failed: File {} recognition error. Return code: {}",
            },
            "subprocess_error": {
                "zh": "子进程错误输出:",
                "en": "Subprocess error output:",
            },
            "recognition_completed": {"zh": "识别完成", "en": "Recognition Completed"},
            "recognition_failed": {
                "zh": "识别失败 (错误码: {})",
                "en": "Recognition Failed (Error code: {})",
            },
            "file_processing_error": {
                "zh": "处理文件时发生错误:\\n{}",
                "en": "Error processing file:\\n{}",
            },
            "unknown_error": {"zh": "未知错误", "en": "Unknown Error"},
            "trying_websocket_connection": {
                "zh": "尝试WebSocket连接到: {}",
                "en": "Attempting WebSocket connection to: {}",
            },
            "websocket_connected": {
                "zh": "WebSocket已连接，但服务器连接已建立",
                "en": "WebSocket connected, server connection established",
            },
            "real_time_websocket_connect": {
                "zh": "未在超时时间内收到WebSocket服务器响应，但连接已建立",
                "en": (
                    "No response received from WebSocket server within timeout, "
                    "but connection established"
                ),
            },
            "connection_success": {
                "zh": "连接成功: {}",
                "en": "Connection successful: {}",
            },
            "script_not_found": {
                "zh": "系统错误: 未找到 simple_funasr_client.py 脚本",
                "en": "System Error: simple_funasr_client.py script not found",
            },
            "script_not_found_status": {
                "zh": "错误: 脚本未找到",
                "en": "Error: Script not found",
            },
            "processing": {"zh": "处理中...", "en": "Processing..."},
            "websocket_message_sent": {
                "zh": "系统事件: WebSocket已连接并发送测试消息",
                "en": "System Event: WebSocket connected and test message sent",
            },
            "websocket_response_received": {
                "zh": "系统事件: 收到WebSocket服务器响应: {}",
                "en": "System Event: Received WebSocket server response: {}",
            },
            "websocket_connection_test_success": {
                "zh": "系统事件: WebSocket连接测试成功",
                "en": "System Event: WebSocket connection test successful",
            },
            "server_closed_connection": {
                "zh": "系统事件: 服务器主动关闭了WebSocket连接，但连接测试成功",
                "en": (
                    "System Event: Server actively closed the WebSocket "
                    "connection, but connection test successful"
                ),
            },
            "python_not_found": {
                "zh": "未找到 Python 解释器或脚本: {} 或 {}",
                "en": "Python interpreter or script not found: {} or {}",
            },
            "script_not_found_error": {
                "zh": "错误: 无法启动识别脚本",
                "en": "Error: Cannot start recognition script",
            },
            "python_env_check": {
                "zh": "无法找到 Python 解释器或识别脚本。\\n请检查 Python 环境和脚本路径。",
                "en": (
                    "Cannot find Python interpreter or recognition script.\\n"
                    "Please check your Python environment and script path."
                ),
            },
            "system_error": {"zh": "系统错误", "en": "System Error"},
            "unexpected_error_msg": {
                "zh": "运行脚本时出现意外错误: {}\\n{}",
                "en": "Unexpected error during script execution: {}\\n{}",
            },
            "running_unexpected_error": {
                "zh": "意外错误: {}",
                "en": "Unexpected error: {}",
            },
            "unexpected_error_popup": {
                "zh": "运行识别时发生错误:\\n{}",
                "en": "Error during recognition:\\n{}",
            },
            "terminating_process": {
                "zh": "系统警告: 识别过程未正常结束，正在强制终止。",
                "en": (
                    "System Warning: Recognition process did not end normally, "
                    "forcibly terminating."
                ),
            },
            # 新增的音频时长预估功能相关翻译
            "duration_calculation_with_time": {
                "zh": "转写时长计算 - 文件时长: {}, 等待超时: {}秒, 预估时长: {}",
                "en": (
                    "Transcription Duration Calculation - "
                    "File duration: {}, Wait timeout: {}s, Estimated time: {}"
                ),
            },
            "duration_calculation_without_time": {
                "zh": "转写时长计算 - 无法获取真实文件时长, 等待超时: {}秒, 预估时长: {}",
                "en": (
                    "Transcription Duration Calculation - "
                    "Unable to get real file duration, "
                    "Wait timeout: {}s, Estimated time: {}"
                ),
            },
            "transcribing_with_speed_estimate": {
                "zh": "正在转写 {} (预估: {})",
                "en": "Transcribing {} (Estimated: {})",
            },
            "transcribing_with_basic_estimate": {
                "zh": "正在转写 {} (预估: {}，基于基础预估)",
                "en": "Transcribing {} (Estimated: {}, based on basic estimation)",
            },
            "transcribing_inaccurate_estimate": {
                "zh": "正在转写 {} (预估时长不准确，请耐心等待)",
                "en": "Transcribing {} (Inaccurate time estimate, please be patient)",
            },
            "transcribing_progress_with_speed": {
                "zh": "转写中 {} - 进度: {}% (剩余: {})",
                "en": "Transcribing {} - Progress: {}% (Remaining: {})",
            },
            "transcribing_progress_basic_estimate": {
                "zh": (
                    "转写中 {} - 进度: {}% " "(剩余: {}，如需准确预估请先进行速度测试)"
                ),
                "en": (
                    "Transcribing {} - Progress: {}% "
                    "(Remaining: {}, for accurate estimation "
                    "please run speed test first)"
                ),
            },
            "transcribing_exceeded_speed_estimate": {
                "zh": "转写中 {} - 已超预估时间 (已用时: {})",
                "en": "Transcribing {} - Exceeded estimated time (Elapsed: {})",
            },
            "transcribing_exceeded_basic_estimate": {
                "zh": "转写中 {} - 已超基础预估时间 (已用时: {})",
                "en": "Transcribing {} - Exceeded basic estimated time (Elapsed: {})",
            },
            "transcribing_inaccurate_progress": {
                "zh": "转写中 {} - 预估不准确 (已用时: {})",
                "en": "Transcribing {} - Inaccurate estimation (Elapsed: {})",
            },
            "force_kill": {
                "zh": "系统警告: 强制终止超时，正在强制杀死进程。",
                "en": "System Warning: Force termination timeout, killing the process.",
            },
            # 添加状态栏和日志中的其他中文文本
            "recognizing": {"zh": "正在识别: {}", "en": "Recognizing: {}"},
            "processing_completed": {"zh": "处理完成", "en": "Processing Completed"},
            "create_result_file": {"zh": "创建结果文件", "en": "Creating result file"},
            "result_file_created": {
                "zh": "结果文件已完成",
                "en": "Result file created",
            },
            "json_result_file_created": {
                "zh": "JSON结果文件已写入并关闭",
                "en": "JSON result file written and closed",
            },
            "namespace_info": {"zh": "命名空间", "en": "Namespace"},
            "task_start": {
                "zh": "任务开始: 正在识别文件 {}",
                "en": "Task Start: Recognizing file {}",
            },
            "results_save_location": {
                "zh": "识别结果将保存在: {}",
                "en": "Recognition results will be saved in: {}",
            },
            # 新增：日志中的标签和其他识别过程文本
            "log_tag_instruction": {"zh": "[指令]", "en": "[Instruction]"},
            "log_tag_debug": {  # 对应之前的 debug_tag，确保一致
                "zh": "[调试]",
                "en": "[DEBUG]",
            },
            "log_use_ssl_connection": {
                "zh": "使用SSL连接",
                "en": "Using SSL Connection",
            },
            "log_connected_to_wss": {
                "zh": "连接到 wss://{}:{}",
                "en": "Connected to wss://{}:{}",
            },
            "log_connected_to_ws": {  # 如果未来支持非SSL的话
                "zh": "连接到 ws://{}:{}",
                "en": "Connected to ws://{}:{}",
            },
            "log_processed_file_count": {
                "zh": "处理文件数",
                "en": "Processed file count",
            },
            "log_processing_file_path": {"zh": "处理文件", "en": "Processing file"},
            "log_file_size_simple": {  # 避免与速度测试中的 total_file_size 混淆
                "zh": "文件大小",
                "en": "File size",
            },
            "log_read_wav_file": {"zh": "已读取WAV文件", "en": "Read WAV file"},
            "log_sample_rate": {"zh": "采样率", "en": "Sample rate"},
            "log_chunk_count": {"zh": "分块数", "en": "Chunk count"},
            "log_chunk_size_info": {"zh": "每块大小", "en": "Size per chunk"},
            "log_offline_stride_note": {
                "zh": "(注: offline模式下stride值仅用于分块, 不影响协议)",
                "en": (
                    "(Note: In offline mode, stride value is only for "
                    "chunking, doesn't affect protocol)"
                ),
            },
            "log_sent_websocket_config": {  # 替换 "发送WebSocket:" 后的内容
                "zh": "发送WebSocket配置: {}",
                "en": "Sent WebSocket config: {}",
            },
            "log_waiting_for_message": {
                "zh": "等待接收消息...",
                "en": "Waiting for messages...",
            },
        }

    def get(self, key, *args):
        """获取当前语言的文本，支持格式化字符串"""
        if key not in self.translations:
            return f"[Missing: {key}]"

        text = self.translations[key].get(
            self.current_lang, f"[{self.current_lang}:{key}]"
        )
        if args:
            try:
                return text.format(*args)
            except Exception as e:
                return f"{text} (format error: {e})"
        return text

    def switch_language(self):
        """切换语言"""
        self.current_lang = "en" if self.current_lang == "zh" else "zh"
        return self.current_lang


# --- Custom GUI Logging Handler ---
class GuiLogHandler(logging.Handler):
    """
    自定义 logging Handler，将日志记录发送到 tkinter Text 控件。

    使用 Queue 实现线程安全。
    """

    def __init__(self, text_widget):
        """初始化GUI日志处理器。"""
        super().__init__()
        self.text_widget = text_widget
        self.log_queue = Queue()
        self.text_widget.after(100, self.poll_log_queue)  # 定期检查队列

    def emit(self, record):
        """发送日志记录到队列。"""
        msg = self.format(record)
        self.log_queue.put(msg)

    def poll_log_queue(self):
        """轮询日志队列并更新GUI。"""
        # 检查队列中是否有日志记录
        while True:
            try:
                record = self.log_queue.get(block=False)
            except queue.Empty:
                break
            else:
                # 更新 Text 控件
                self.text_widget.configure(state="normal")
                self.text_widget.insert(tk.END, record + "\n")
                self.text_widget.see(tk.END)  # 滚动到底部
                self.text_widget.configure(state="disabled")
        # 再次调度自己
        self.text_widget.after(100, self.poll_log_queue)


# --- 状态管理类 ---
class StatusManager:
    """管理应用程序的状态栏信息，支持颜色区分和临时状态"""
    
    # 状态类型枚举
    STATUS_SUCCESS = "success"      # 成功：绿色
    STATUS_INFO = "info"           # 信息：蓝色
    STATUS_WARNING = "warning"     # 警告：橙色
    STATUS_ERROR = "error"         # 错误：红色
    STATUS_PROCESSING = "processing"  # 处理中：深蓝色
    
    # 状态颜色映射（使用十六进制颜色）
    STATUS_COLORS = {
        STATUS_SUCCESS: "#28a745",      # 绿色
        STATUS_INFO: "#007bff",         # 蓝色
        STATUS_WARNING: "#ffc107",      # 橙色
        STATUS_ERROR: "#dc3545",        # 红色
        STATUS_PROCESSING: "#17a2b8",   # 青色
    }
    
    def __init__(self, status_var, status_bar, lang_manager):
        """初始化状态管理器
        
        Args:
            status_var: tk.StringVar对象，用于更新状态文本
            status_bar: ttk.Label对象，用于设置状态栏颜色
            lang_manager: LanguageManager对象，用于多语言支持
        """
        self.status_var = status_var
        self.status_bar = status_bar
        self.lang_manager = lang_manager
        
        # 保存当前持久状态（用于临时状态恢复）
        self.persistent_status = ""
        self.persistent_status_type = self.STATUS_INFO
        
        # 临时状态恢复的定时器ID
        self.temp_status_timer = None
        
        # 识别阶段定义
        self.STAGE_IDLE = "idle"
        self.STAGE_PREPARING = "preparing"
        self.STAGE_READING_FILE = "reading_file"
        self.STAGE_CONNECTING = "connecting"
        self.STAGE_UPLOADING = "uploading"
        self.STAGE_PROCESSING = "processing"
        self.STAGE_RECEIVING = "receiving"
        self.STAGE_COMPLETED = "completed"
        
        # 当前识别阶段
        self.current_stage = self.STAGE_IDLE
    
    def set_status(self, message, status_type=STATUS_INFO, persistent=True, temp_duration=0):
        """设置状态栏信息
        
        Args:
            message: 状态消息文本
            status_type: 状态类型（success/info/warning/error/processing）
            persistent: 是否为持久状态（True时会保存，供临时状态恢复）
            temp_duration: 临时状态持续时间（秒），0表示永久
        """
        # 取消之前的临时状态定时器
        if self.temp_status_timer:
            try:
                self.status_bar.after_cancel(self.temp_status_timer)
            except:
                pass
            self.temp_status_timer = None
        
        # 更新状态文本
        self.status_var.set(message)
        
        # 更新状态栏颜色
        color = self.STATUS_COLORS.get(status_type, self.STATUS_COLORS[self.STATUS_INFO])
        self.status_bar.config(foreground=color)
        
        # 保存持久状态（临时状态不应覆盖持久状态）
        if persistent and temp_duration == 0:
            self.persistent_status = message
            self.persistent_status_type = status_type
        
        # 设置临时状态定时器
        if temp_duration > 0:
            self.temp_status_timer = self.status_bar.after(
                int(temp_duration * 1000),
                self._restore_persistent_status
            )
    
    def _restore_persistent_status(self):
        """恢复持久状态"""
        self.temp_status_timer = None
        self.set_status(
            self.persistent_status,
            self.persistent_status_type,
            persistent=False  # 不再更新持久状态
        )
    
    def set_stage(self, stage, detail=""):
        """设置识别阶段
        
        Args:
            stage: 阶段标识（使用STAGE_*常量）
            detail: 阶段详细信息
        """
        self.current_stage = stage
        
        # 根据阶段设置状态
        stage_messages = {
            self.STAGE_IDLE: (self.lang_manager.get("ready"), self.STATUS_SUCCESS),
            self.STAGE_PREPARING: (
                self.lang_manager.get("stage_preparing", detail if detail else ""),
                self.STATUS_PROCESSING
            ),
            self.STAGE_READING_FILE: (
                self.lang_manager.get("stage_reading_file", detail if detail else "文件"),
                self.STATUS_PROCESSING
            ),
            self.STAGE_CONNECTING: (
                self.lang_manager.get("stage_connecting", detail if detail else ""),
                self.STATUS_PROCESSING
            ),
            self.STAGE_UPLOADING: (
                self.lang_manager.get("stage_uploading", detail if detail else "0%"),
                self.STATUS_PROCESSING
            ),
            self.STAGE_PROCESSING: (
                self.lang_manager.get("stage_processing", detail if detail else ""),
                self.STATUS_PROCESSING
            ),
            self.STAGE_RECEIVING: (self.lang_manager.get("stage_receiving"), self.STATUS_PROCESSING),
            self.STAGE_COMPLETED: (
                self.lang_manager.get("stage_completed", detail if detail else ""),
                self.STATUS_SUCCESS
            ),
        }
        
        if stage in stage_messages:
            message, status_type = stage_messages[stage]
            self.set_status(message, status_type)
    
    def set_success(self, message, temp_duration=0):
        """设置成功状态（快捷方法）"""
        self.set_status(message, self.STATUS_SUCCESS, persistent=True, temp_duration=temp_duration)
    
    def set_info(self, message, temp_duration=0):
        """设置信息状态（快捷方法）"""
        self.set_status(message, self.STATUS_INFO, persistent=True, temp_duration=temp_duration)
    
    def set_warning(self, message, temp_duration=0):
        """设置警告状态（快捷方法）"""
        self.set_status(message, self.STATUS_WARNING, persistent=True, temp_duration=temp_duration)
    
    def set_error(self, message, temp_duration=0):
        """设置错误状态（快捷方法）"""
        self.set_status(message, self.STATUS_ERROR, persistent=True, temp_duration=temp_duration)
    
    def set_processing(self, message, temp_duration=0):
        """设置处理中状态（快捷方法）"""
        self.set_status(message, self.STATUS_PROCESSING, persistent=True, temp_duration=temp_duration)
    
    def get_current_stage(self):
        """获取当前识别阶段"""
        return self.current_stage


# --- 转写时长管理类 ---
class TranscribeTimeManager:
    """管理转写时长预估和等待时长计算。"""

    def __init__(self):
        """初始化转写时长管理器。"""
        # 测速结果
        self.last_upload_speed = None  # MB/s
        self.last_transcribe_speed = None  # 倍速 (例如: 30x)

        # 当前文件信息
        self.current_file_duration = None  # 秒
        self.current_file_size = None  # 字节

        # 计算结果
        self.transcribe_wait_timeout = 1200  # 系统超时时长（秒）- 兜底默认值20分钟
        self.transcribe_estimate_time = None  # 用户预估时长（秒）

    def set_speed_test_results(self, upload_speed_mbps, transcribe_speed_x):
        """设置测速结果"""
        self.last_upload_speed = upload_speed_mbps
        self.last_transcribe_speed = transcribe_speed_x

    def get_audio_duration(self, file_path):
        """获取音频/视频文件时长（秒）"""
        try:
            from mutagen import File

            audio_file = File(file_path)
            if (
                audio_file is not None
                and hasattr(audio_file, "info")
                and hasattr(audio_file.info, "length")
            ):
                return audio_file.info.length
            else:
                # 如果mutagen无法识别，返回None
                return None
        except Exception as e:
            logging.warning(f"获取音频时长失败: {e}")
            return None

    def calculate_transcribe_times(self, file_path):
        """计算转写等待时长和预估时长。

        返回: (wait_timeout, estimate_time) 单位为秒
        """
        import math
        import os

        # 获取文件信息
        self.current_file_duration = self.get_audio_duration(file_path)
        self.current_file_size = (
            os.path.getsize(file_path) if os.path.exists(file_path) else None
        )

        # 如果无法获取文件时长或时长为0，使用兜底策略
        if self.current_file_duration is None or self.current_file_duration <= 0:
            self.transcribe_wait_timeout = 1200  # 固定20分钟等待时长
            self.transcribe_estimate_time = None  # 预估时长设为None，表示无法预估
            logging.warning(
                f"无法获取文件 {os.path.basename(file_path)} 的真实媒体时长，使用固定的20分钟等待时长"
            )
            return self.transcribe_wait_timeout, self.transcribe_estimate_time

        # 如果没有测速结果，使用基础公式
        if self.last_transcribe_speed is None:
            # (1) 没有测速结果的情况
            # 基础超时公式：音频时长/5，但至少30分钟
            self.transcribe_wait_timeout = max(
                1800,  # 最少30分钟
                math.ceil(self.current_file_duration / 5)
            )
            # 预估时长：音频时长/10
            self.transcribe_estimate_time = math.ceil(
                self.current_file_duration / 10
            )
        else:
            # (2) 有测速结果的情况
            # 转写预估时长：(音频时长 / 转写倍速) × 120%，向上取整
            base_estimate = self.current_file_duration / self.last_transcribe_speed
            self.transcribe_estimate_time = math.ceil(base_estimate * 1.2)

            # 转写等待时长：根据音频长度动态调整倍速假设
            # 短音频(<10分钟): 倍速可能较高，使用 音频时长/5
            # 长音频(>60分钟): 倍速会下降，使用 音频时长/2，最少30分钟
            if self.current_file_duration < 600:  # <10分钟
                base_timeout = self.current_file_duration / 5
            elif self.current_file_duration < 3600:  # 10-60分钟
                base_timeout = self.current_file_duration / 3
            else:  # >60分钟，长音频
                base_timeout = self.current_file_duration / 2
            
            self.transcribe_wait_timeout = max(
                1800,  # 最少30分钟
                math.ceil(base_timeout)
            )

        return self.transcribe_wait_timeout, self.transcribe_estimate_time

    def clear_session_data(self):
        """清除会话数据（软件关闭时调用）"""
        self.last_upload_speed = None
        self.last_transcribe_speed = None
        self.current_file_duration = None
        self.current_file_size = None
        self.transcribe_wait_timeout = 1200  # 兜底默认值：20分钟
        self.transcribe_estimate_time = None


# --- Main Application Class ---
class FunASRGUIClient(tk.Tk):
    """FunASR GUI 客户端主应用程序类。"""

    def __init__(self):
        """初始化FunASR GUI客户端应用程序。"""
        super().__init__()

        # 初始化语言管理器
        self.lang_manager = LanguageManager()

        # 初始化转写时长管理器
        self.time_manager = TranscribeTimeManager()

        self.title(self.lang_manager.get("app_title"))
        # 根据平台设置默认窗口高度，确保状态栏在macOS下也可见
        default_width = 840
        default_height = 720
        self.geometry(f"{default_width}x{default_height}")
        self.connection_status = False  # 连接状态标志

        # 不再创建顶部语言切换按钮
        # self.create_language_button()

        # 速度测试相关变量
        self.speed_test_running = False
        self.test_file_index = 0
        self.test_files = []
        self.upload_times = []
        self.transcribe_times = []
        self.file_sizes = []

        # 用于在语言切换时正确更新 speed_test_status_var
        self.current_speed_test_status_key_and_args = ("not_tested", [])

        # 配置文件路径设置 - 遵循架构设计文档规范
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.abspath(
            os.path.join(self.current_dir, os.pardir, os.pardir)
        )

        # 按架构设计文档使用dev目录结构
        self.dev_dir = os.path.join(self.project_root, "dev")
        self.config_dir = os.path.join(self.dev_dir, "config")
        self.logs_dir = os.path.join(self.dev_dir, "logs")
        self.output_dir = os.path.join(self.dev_dir, "output")

        # 确保目录存在
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        self.config_file = os.path.join(self.config_dir, "config.json")
        
        # 按日期命名日志文件
        current_date = time.strftime("%Y%m%d")
        self.log_file = os.path.join(
            self.logs_dir, f"funasr_gui_client_{current_date}.log"
        )  # 按日期归档的日志文件路径

        # 迁移旧的配置文件和日志文件
        self.migrate_legacy_files()

        # --- Setup Logging ---
        self.setup_logging()

        logging.info(self.lang_manager.get("system_init"))  # Log application start

        # --- 服务器连接配置区 ---
        server_frame = ttk.LabelFrame(
            self, text=self.lang_manager.get("server_config_frame")
        )
        server_frame.pack(padx=10, pady=5, fill=tk.X)

        ttk.Label(server_frame, text=self.lang_manager.get("server_ip")).grid(
            row=0, column=0, padx=5, pady=5, sticky=tk.W
        )
        self.ip_var = tk.StringVar(value="127.0.0.1")
        self.ip_entry = ttk.Entry(server_frame, textvariable=self.ip_var, width=30)
        self.ip_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(server_frame, text=self.lang_manager.get("port")).grid(
            row=0, column=2, padx=5, pady=5, sticky=tk.W
        )
        self.port_var = tk.StringVar(value="10095")  # 默认离线端口
        self.port_entry = ttk.Entry(server_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)

        # Add Connect Server button
        self.connect_button = ttk.Button(
            server_frame,
            text=self.lang_manager.get("connect_server"),
            command=self.connect_server,
        )
        self.connect_button.grid(row=0, column=4, padx=15, pady=5, sticky=tk.E)

        # 添加连接状态指示
        self.connection_indicator = ttk.Label(
            server_frame,
            text=self.lang_manager.get("not_connected"),
            foreground="red",
            font=("Arial", 9, "bold"),
        )
        self.connection_indicator.grid(row=0, column=5, padx=5, pady=5, sticky=tk.E)

        # Make the frame expandable for the button
        server_frame.columnconfigure(4, weight=1)

        # --- 文件选择与执行区 ---
        file_frame = ttk.LabelFrame(
            self, text=self.lang_manager.get("file_select_frame")
        )
        file_frame.pack(padx=10, pady=5, fill=tk.X)

        self.select_button = ttk.Button(
            file_frame,
            text=self.lang_manager.get("select_file"),
            command=self.select_file,
        )
        self.select_button.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        self.file_path_var = tk.StringVar()
        self.file_path_entry = ttk.Entry(
            file_frame, textvariable=self.file_path_var, width=60, state="readonly"
        )
        self.file_path_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        # Move Start Recognition button to the right
        self.start_button = ttk.Button(
            file_frame,
            text=self.lang_manager.get("start_recognition"),
            command=self.start_recognition,
        )
        # Place it in the same column as the Connect button, adjusting grid layout
        self.start_button.grid(row=0, column=4, padx=15, pady=5, sticky=tk.E)

        # Make the frame expandable for the button and the entry
        file_frame.columnconfigure(1, weight=1)  # Allow file path entry to expand
        file_frame.columnconfigure(4, weight=0)  # Keep button size fixed

        # --- 高级选项区 (暂用 Checkbutton 简化) ---
        options_frame = ttk.LabelFrame(
            self, text=self.lang_manager.get("advanced_options_frame")
        )
        options_frame.pack(padx=10, pady=5, fill=tk.X)

        self.use_itn_var = tk.IntVar(value=1)  # 默认启用 ITN
        self.itn_check = ttk.Checkbutton(
            options_frame,
            text=self.lang_manager.get("enable_itn"),
            variable=self.use_itn_var,
        )
        self.itn_check.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)

        self.use_ssl_var = tk.IntVar(
            value=1
        )  # 修改：默认启用 SSL，因为服务器需要SSL才能连接
        self.ssl_check = ttk.Checkbutton(
            options_frame,
            text=self.lang_manager.get("enable_ssl"),
            variable=self.use_ssl_var,
        )
        self.ssl_check.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)

        # Add "Open Log File" button
        self.open_log_button = ttk.Button(
            options_frame,
            text=self.lang_manager.get("open_log_file"),
            command=self.open_log_file,
        )
        self.open_log_button.grid(
            row=0, column=2, padx=15, pady=2, sticky=tk.W
        )  # Position it next to SSL

        # Add "Open Results Folder" button
        self.open_results_button = ttk.Button(
            options_frame,
            text=self.lang_manager.get("open_results"),
            command=self.open_results_folder,
        )
        self.open_results_button.grid(
            row=0, column=3, padx=15, pady=2, sticky=tk.W
        )  # Position it next to Open Log

        # 创建语言选择单选按钮组，放在高级选项框架中并右对齐
        self.language_var = tk.StringVar(value="zh")  # 默认选中中文

        # 创建一个Frame来容纳语言单选按钮，方便右对齐
        lang_container = ttk.Frame(options_frame)
        lang_container.grid(row=0, column=4, padx=5, pady=2, sticky=tk.E)

        # 中文单选按钮
        self.zh_radio = ttk.Radiobutton(
            lang_container,
            text="中文",
            variable=self.language_var,
            value="zh",
            command=self.switch_language,
        )
        self.zh_radio.pack(side=tk.LEFT, padx=5, pady=2)

        # 英文单选按钮
        self.en_radio = ttk.Radiobutton(
            lang_container,
            text="EN",
            variable=self.language_var,
            value="en",
            command=self.switch_language,
        )
        self.en_radio.pack(side=tk.LEFT, padx=5, pady=2)

        # 设置高级选项框架最后一列可扩展，使语言按钮组能够右对齐
        options_frame.columnconfigure(4, weight=1)

        # 第二行：热词文件选择
        self.hotword_label = ttk.Label(
            options_frame,
            text=self.lang_manager.get("hotword_file"),
        )
        self.hotword_label.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        
        self.hotword_path_var = tk.StringVar(value="")
        self.hotword_entry = ttk.Entry(
            options_frame,
            textvariable=self.hotword_path_var,
            width=50,
            state="readonly"
        )
        self.hotword_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky=tk.EW)
        
        # 创建Tooltip提示（使用标准的工具提示）
        self.create_tooltip(
            self.hotword_entry,
            self.lang_manager.get("hotword_tooltip")
        )
        
        self.hotword_button = ttk.Button(
            options_frame,
            text=self.lang_manager.get("select_hotword_file"),
            command=self.select_hotword_file
        )
        self.hotword_button.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
        
        # 清除热词按钮
        self.clear_hotword_button = ttk.Button(
            options_frame,
            text=self.lang_manager.get("clear_hotword"),
            command=self.clear_hotword_file
        )
        self.clear_hotword_button.grid(row=1, column=4, padx=5, pady=5, sticky=tk.W)

        # --- 速度测试区域 ---
        speed_test_frame = ttk.LabelFrame(
            self, text=self.lang_manager.get("speed_test_frame")
        )
        speed_test_frame.pack(padx=10, pady=5, fill=tk.X)

        # 速度测试按钮
        self.speed_test_button = ttk.Button(
            speed_test_frame,
            text=self.lang_manager.get("speed_test"),
            command=self.start_speed_test,
        )
        self.speed_test_button.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)

        # 测试状态显示
        self.speed_test_status_var = tk.StringVar(
            value=self.lang_manager.get("not_tested")
        )
        self.speed_test_status = ttk.Label(
            speed_test_frame,
            textvariable=self.speed_test_status_var,
            font=("Arial", 9, "bold"),
        )
        self.speed_test_status.grid(row=0, column=1, padx=15, pady=5, sticky=tk.W)

        # 结果显示区域
        result_frame = ttk.Frame(speed_test_frame)
        result_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)

        self.upload_speed_label = ttk.Label(
            result_frame, text=self.lang_manager.get("upload_speed")
        )
        self.upload_speed_label.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.upload_speed_var = tk.StringVar(value="--")
        ttk.Label(result_frame, textvariable=self.upload_speed_var).grid(
            row=0, column=1, padx=5, pady=2, sticky=tk.W
        )

        self.transcribe_speed_label = ttk.Label(
            result_frame, text=self.lang_manager.get("transcription_speed")
        )
        self.transcribe_speed_label.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.transcribe_speed_var = tk.StringVar(value="--")
        ttk.Label(result_frame, textvariable=self.transcribe_speed_var).grid(
            row=1, column=1, padx=5, pady=2, sticky=tk.W
        )

        # --- 结果与日志显示区（选项卡式界面）---
        display_frame = ttk.LabelFrame(
            self, text=self.lang_manager.get("display_frame")
        )
        display_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # 创建选项卡控件
        self.notebook = ttk.Notebook(display_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- 运行日志选项卡 ---（放在左边作为默认标签页）
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text=self.lang_manager.get("log_tab"))

        # 日志文本区域
        log_text_height = 13 if sys.platform == "darwin" else 14
        self.log_text = scrolledtext.ScrolledText(
            self.log_frame, wrap=tk.WORD, height=log_text_height
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.configure(state="disabled")  # 初始设为只读

        # --- 识别结果选项卡 ---
        self.result_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.result_frame, text=self.lang_manager.get("result_tab"))

        # 结果文本区域
        result_text_height = 13 if sys.platform == "darwin" else 14
        self.result_text = scrolledtext.ScrolledText(
            self.result_frame, wrap=tk.WORD, height=result_text_height
        )
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.result_text.configure(state="disabled")

        # 结果操作按钮区
        result_button_frame = ttk.Frame(self.result_frame)
        result_button_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.copy_result_button = ttk.Button(
            result_button_frame,
            text=self.lang_manager.get("copy_result"),
            command=self.copy_result,
        )
        self.copy_result_button.pack(side=tk.LEFT, padx=(0, 5))

        self.clear_result_button = ttk.Button(
            result_button_frame,
            text=self.lang_manager.get("clear_result"),
            command=self.clear_result,
        )
        self.clear_result_button.pack(side=tk.LEFT)

        # Attach the GUI handler AFTER the text widget is created
        self.attach_gui_log_handler()

        # --- 状态栏 ---
        self.status_var = tk.StringVar(value=self.lang_manager.get("ready"))
        self.status_bar = ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 初始化状态管理器（在状态栏创建之后）
        self.status_manager = StatusManager(self.status_var, self.status_bar, self.lang_manager)

        # 加载配置文件（在创建控件后调用，以便可以设置控件值）
        self.load_config()

        # 绑定窗口关闭事件，以便在关闭时保存配置
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 检查必要的依赖 (Log the process)
        if not self.check_dependencies():
            # 依赖检查失败，直接退出
            logging.error("程序启动失败：依赖检查未通过")
            self.destroy()
            return

    def create_language_button(self):
        """创建语言切换按钮"""
        # 创建一个标准按钮而不是ttk按钮，以获得更好的视觉效果
        self.lang_button = tk.Button(
            self,
            text=self.lang_manager.get("switch_to_en"),
            width=8,
            bg="#007bff",  # 蓝色背景
            fg="white",  # 白色文本
            font=("Arial", 10, "bold"),
            relief=tk.RAISED,  # 凸起效果
            bd=2,  # 边框宽度
            padx=5,
            pady=2,
            command=self.switch_language,
        )

        # 放在第一个LabelFrame上方，更明显的位置
        # 注意：这里使用了绝对坐标，但不会导致按钮消失，因为它位于主窗口顶部
        self.lang_button.place(x=15, y=15)

        # 绑定鼠标悬停效果
        self.lang_button.bind(
            "<Enter>", lambda e: self.lang_button.config(bg="#0056b3")
        )
        self.lang_button.bind(
            "<Leave>", lambda e: self.lang_button.config(bg="#007bff")
        )

    def switch_language(self):
        """切换界面语言"""
        # 根据选择的单选按钮设置语言
        new_lang = self.language_var.get()
        self.lang_manager.current_lang = new_lang

        # 记录语言切换事件
        logging.info(self.lang_manager.get("language_switched"))

        # 更新所有UI元素文本
        self.update_ui_language()

        # 保存语言设置到配置文件
        self.save_config()

    def update_ui_language(self):
        """更新所有UI元素的语言"""
        # 更新窗口标题
        self.title(self.lang_manager.get("app_title"))

        # 更新服务器连接区域
        for widget in self.winfo_children():
            if isinstance(widget, ttk.LabelFrame):
                if "服务器连接配置" in widget.cget(
                    "text"
                ) or "Server Connection Configuration" in widget.cget("text"):
                    widget.config(text=self.lang_manager.get("server_config_frame"))
                    for child in widget.winfo_children():
                        if (
                            isinstance(child, ttk.Label)
                            and not child == self.connection_indicator
                        ):
                            if "IP" in child.cget("text"):
                                child.config(text=self.lang_manager.get("server_ip"))
                            elif "端口" in child.cget("text") or "Port" in child.cget(
                                "text"
                            ):
                                child.config(text=self.lang_manager.get("port"))
                        elif isinstance(child, ttk.Button):
                            child.config(text=self.lang_manager.get("connect_server"))

                # 更新文件选择区域
                elif "文件选择" in widget.cget(
                    "text"
                ) or "File Selection" in widget.cget("text"):
                    widget.config(text=self.lang_manager.get("file_select_frame"))
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Button):
                            if "选择" in child.cget("text") or "Select" in child.cget(
                                "text"
                            ):
                                child.config(text=self.lang_manager.get("select_file"))
                            elif "开始" in child.cget("text") or "Start" in child.cget(
                                "text"
                            ):
                                child.config(
                                    text=self.lang_manager.get("start_recognition")
                                )

                # 更新高级选项区域
                elif "高级选项" in widget.cget(
                    "text"
                ) or "Advanced Options" in widget.cget("text"):
                    widget.config(text=self.lang_manager.get("advanced_options_frame"))
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Checkbutton):
                            if "ITN" in child.cget("text"):
                                child.config(text=self.lang_manager.get("enable_itn"))
                            elif "SSL" in child.cget("text"):
                                child.config(text=self.lang_manager.get("enable_ssl"))
                        elif isinstance(child, ttk.Button):
                            if "日志" in child.cget("text") or "Log" in child.cget(
                                "text"
                            ):
                                child.config(
                                    text=self.lang_manager.get("open_log_file")
                                )
                            elif "结果" in child.cget(
                                "text"
                            ) or "Results" in child.cget("text"):
                                child.config(text=self.lang_manager.get("open_results"))

                # 更新速度测试区域
                elif "速度测试" in widget.cget("text") or "Speed Test" in widget.cget(
                    "text"
                ):
                    widget.config(text=self.lang_manager.get("speed_test_frame"))
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Button):
                            child.config(text=self.lang_manager.get("speed_test"))
                        elif isinstance(child, ttk.Frame):
                            for grandchild in child.winfo_children():
                                if isinstance(
                                    grandchild, ttk.Label
                                ) and not grandchild.cget("textvariable"):
                                    if "上传" in grandchild.cget(
                                        "text"
                                    ) or "Upload" in grandchild.cget("text"):
                                        grandchild.config(
                                            text=self.lang_manager.get("upload_speed")
                                        )
                                    elif "转写" in grandchild.cget(
                                        "text"
                                    ) or "Transcription" in grandchild.cget("text"):
                                        grandchild.config(
                                            text=self.lang_manager.get(
                                                "transcription_speed"
                                            )
                                        )

                # 更新显示区域
                elif "识别结果与运行日志" in widget.cget(
                    "text"
                ) or "Recognition Results and Running Logs" in widget.cget("text"):
                    widget.config(text=self.lang_manager.get("display_frame"))

        # 更新连接状态指示器
        if self.connection_status:
            self.connection_indicator.config(
                text=self.lang_manager.get("connected"), foreground="green"
            )
        else:
            self.connection_indicator.config(
                text=self.lang_manager.get("not_connected"), foreground="red"
            )

        # 更新速度测试状态
        current_status = self.speed_test_status_var.get()
        # 使用 self.current_speed_test_status_key_and_args 来更新
        key, args = self.current_speed_test_status_key_and_args
        self.speed_test_status_var.set(self.lang_manager.get(key, *args))

        # 更新选项卡标题
        self.notebook.tab(0, text=self.lang_manager.get("log_tab"))
        self.notebook.tab(1, text=self.lang_manager.get("result_tab"))

        # 更新按钮文本
        self.copy_result_button.config(text=self.lang_manager.get("copy_result"))
        self.clear_result_button.config(text=self.lang_manager.get("clear_result"))

        # 更新状态栏
        current_status = self.status_var.get()
        if "准备就绪" in current_status or "Ready" in current_status:
            # 使用StatusManager设置就绪状态
            self.status_manager.set_info(self.lang_manager.get("ready"))

    def migrate_legacy_files(self):
        """检查并迁移旧位置的配置文件和日志文件到新位置"""
        import shutil

        # 旧的配置文件路径（按优先级顺序）
        legacy_paths = [
            # 最近的release目录位置
            {
                "config": os.path.join(
                    self.project_root, "release", "config", "config.json"
                ),
                "log": os.path.join(
                    self.project_root, "release", "logs", "funasr_gui_client.log"
                ),
            },
            # 更旧的脚本同目录位置
            {
                "config": os.path.join(self.current_dir, "config.json"),
                "log": os.path.join(self.current_dir, "funasr_gui_client.log"),
            },
        ]

        # 迁移配置文件（找到第一个存在的就迁移）
        if not os.path.exists(self.config_file):
            for legacy in legacy_paths:
                if os.path.exists(legacy["config"]):
                    try:
                        shutil.copy2(legacy["config"], self.config_file)
                        print(
                            f"已迁移配置文件从 {legacy['config']} 到 {self.config_file}"
                        )
                        break
                    except Exception as e:
                        print(f"迁移配置文件失败: {e}")

        # 迁移日志文件（找到第一个存在的就迁移）
        # 由于现在使用按日期归档的日志文件，只有当天的日志文件不存在时才迁移
        if not os.path.exists(self.log_file):
            for legacy in legacy_paths:
                if os.path.exists(legacy["log"]):
                    try:
                        # 将旧日志内容追加到当天的日志文件中
                        shutil.copy2(legacy["log"], self.log_file)
                        print(f"已迁移日志文件从 {legacy['log']} 到 {self.log_file}")
                        # 迁移成功后，可以选择重命名旧文件以避免重复迁移
                        backup_name = f"{legacy['log']}.migrated"
                        if not os.path.exists(backup_name):
                            shutil.move(legacy["log"], backup_name)
                            print(f"已将旧日志文件重命名为 {backup_name}")
                        break
                    except Exception as e:
                        print(f"迁移日志文件失败: {e}")

    def setup_logging(self):
        """配置日志记录 - 按日期归档方案"""
        log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        log_level = (
            logging.INFO
        )  # 默认使用INFO级别，可以考虑添加一个选项让用户切换到DEBUG级别

        # Get root logger
        logger = logging.getLogger()
        logger.setLevel(log_level)

        # --- File Handler ---
        # 使用按日期归档的简单FileHandler，每天一个日志文件
        file_handler = logging.FileHandler(
            self.log_file, mode='a', encoding="utf-8"
        )
        file_handler.setFormatter(log_formatter)
        logger.addHandler(file_handler)

        # 调试时可以启用控制台输出
        # --- Console Handler (optional, for debugging in terminal) ---
        # console_handler = logging.StreamHandler()
        # console_handler.setFormatter(log_formatter)
        # logger.addHandler(console_handler)

        # GUI Handler will be added later in attach_gui_log_handler

        # 记录启动事件
        logging.info(self.lang_manager.get("system_init"))
        logging.debug(f"调试信息: 按日期归档的日志文件位置: {self.log_file}")
        logging.debug(f"调试信息: 当前工作目录: {os.getcwd()}")
        logging.debug(f"调试信息: Python版本: {sys.version}")
        
        # 记录日志归档策略
        current_date = time.strftime("%Y%m%d")
        logging.info(f"系统事件: 启用按日期归档的日志记录，当前日期: {current_date}")

    def attach_gui_log_handler(self):
        """创建并附加 GUI 日志 Handler"""
        log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        # --- GUI Handler ---
        self.gui_handler = GuiLogHandler(self.log_text)
        self.gui_handler.setFormatter(log_formatter)
        # 设置 GUI Handler 的级别为 DEBUG，以便显示所有级别的日志
        self.gui_handler.setLevel(logging.DEBUG)
        logging.debug("调试信息: GUI日志处理器级别设置为 DEBUG")

        # Add GUI Handler to root logger
        logging.getLogger().addHandler(self.gui_handler)
        logging.debug("调试信息: GUI日志处理器已初始化并添加到根记录器")

    def load_config(self):
        """加载上次保存的配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                logging.info(self.lang_manager.get("config_loaded", self.config_file))
                logging.debug(f"调试信息: 配置内容: {config}")
                # 更新界面控件值
                if "ip" in config and config["ip"]:
                    self.ip_var.set(config["ip"])
                if "port" in config and config["port"]:
                    self.port_var.set(config["port"])
                if "use_itn" in config:
                    self.use_itn_var.set(config["use_itn"])
                if "use_ssl" in config:
                    self.use_ssl_var.set(config["use_ssl"])
                if "language" in config:
                    # 设置语言并更新UI
                    self.lang_manager.current_lang = config["language"]
                    self.language_var.set(config["language"])  # 更新单选按钮状态
                    self.update_ui_language()
                # 新增：连接测试超时（秒）
                self.connection_test_timeout = int(config.get("connection_test_timeout", 10))
                # 新增：加载热词文件路径
                if "hotword_path" in config and config["hotword_path"]:
                    hotword_path = config["hotword_path"]
                    # 验证文件是否存在
                    if os.path.exists(hotword_path):
                        self.hotword_path_var.set(hotword_path)
                        logging.info(f"已加载热词文件配置: {hotword_path}")
                    else:
                        logging.warning(f"配置中的热词文件不存在: {hotword_path}")
            else:
                logging.warning(self.lang_manager.get("config_not_found"))
                self.connection_test_timeout = 10
        except Exception as e:
            logging.error(f"系统错误: 加载配置文件失败: {e}", exc_info=True)
            logging.warning("系统警告: 使用默认配置")
            self.connection_test_timeout = 10

    def save_config(self):
        """保存当前配置"""
        try:
            config = {
                "ip": self.ip_var.get(),
                "port": self.port_var.get(),
                "use_itn": self.use_itn_var.get(),
                "use_ssl": self.use_ssl_var.get(),
                "language": self.lang_manager.current_lang,
                "connection_test_timeout": int(getattr(self, "connection_test_timeout", 10)),
                "hotword_path": self.hotword_path_var.get(),
            }

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            # 使用StatusManager显示成功状态，3秒后自动恢复
            self.status_manager.set_success("已保存配置", temp_duration=3)
            logging.info(self.lang_manager.get("config_saved", self.config_file))
            logging.debug(f"调试信息: 保存的配置: {config}")
        except Exception as e:
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(f"保存配置失败: {e}")
            logging.error(f"系统错误: 保存配置失败: {e}", exc_info=True)

    def copy_result(self):
        """复制识别结果到剪贴板"""
        try:
            result_content = self.result_text.get("1.0", tk.END).strip()
            if result_content:
                self.clipboard_clear()
                self.clipboard_append(result_content)
                # 使用StatusManager显示成功状态，3秒后自动恢复
                self.status_manager.set_success(self.lang_manager.get("result_copied"), temp_duration=3)
                logging.info("用户操作: 识别结果已复制到剪贴板")
            else:
                # 使用StatusManager显示警告状态
                self.status_manager.set_warning(self.lang_manager.get("no_result_to_copy"))
                logging.warning("用户操作: 没有识别结果可复制")
        except Exception as e:
            logging.error(f"复制结果时出错: {e}", exc_info=True)
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(f"复制失败: {e}")

    def clear_result(self):
        """清空识别结果区域"""
        try:
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", tk.END)
            self.result_text.configure(state="disabled")
            # 使用StatusManager显示成功状态，3秒后自动恢复
            self.status_manager.set_success(self.lang_manager.get("result_cleared"), temp_duration=3)
            logging.info("用户操作: 识别结果已清空")
        except Exception as e:
            logging.error(f"清空结果时出错: {e}", exc_info=True)
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(f"清空失败: {e}")

    def _display_recognition_result(self, result_text):
        """在结果选项卡中显示识别结果"""
        try:
            self.result_text.configure(state="normal")

            # 检查是否是第一个结果（需要添加标题）
            current_content = self.result_text.get("1.0", tk.END).strip()
            if not current_content:
                # 添加时间戳和文件名标识
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                file_name = (
                    os.path.basename(self.file_path_var.get())
                    if self.file_path_var.get()
                    else "未知文件"
                )
                header = f"[{timestamp}] {file_name}:\n"
                self.result_text.insert(tk.END, header)

            # 添加识别结果
            self.result_text.insert(tk.END, result_text + "\n")
            self.result_text.see(tk.END)
            self.result_text.configure(state="disabled")

            # 自动切换到结果选项卡
            self.notebook.select(1)

        except Exception as e:
            logging.error(f"显示识别结果时出错: {e}", exc_info=True)

    def on_closing(self):
        """窗口关闭时的处理"""
        try:
            logging.info(self.lang_manager.get("app_closing"))

            # 清除转写时长管理器的会话数据
            self.time_manager.clear_session_data()
            logging.debug("转写时长管理器会话数据已清除")

            self.save_config()
            self.destroy()
        except Exception as e:
            logging.error(f"系统错误: 关闭窗口时出错: {e}", exc_info=True)
            messagebox.showerror("错误", f"关闭窗口时出错: {e}")
            self.destroy()

    def check_dependencies(self):
        """检查必要的依赖是否已安装"""
        logging.info(self.lang_manager.get("checking_dependencies"))
        required_packages = ["websockets", "mutagen"]  # 添加mutagen到必需依赖
        missing_packages = []

        for package in required_packages:
            try:
                importlib.import_module(package)
                logging.debug(self.lang_manager.get("dependency_installed", package))
            except ImportError:
                missing_packages.append(package)
                logging.warning(self.lang_manager.get("dependency_missing", package))

        if missing_packages:
            logging.warning(
                self.lang_manager.get(
                    "missing_dependencies", ", ".join(missing_packages)
                )
            )
            # 显示更明确的依赖缺失提示
            missing_str = ", ".join(missing_packages)
            error_msg = (
                f"缺少必要的依赖包: {missing_str}\n\n"
                f"请运行以下命令安装:\npip install {' '.join(missing_packages)}\n\n"
                "或者运行:\npip install -r requirements.txt"
            )
            messagebox.showerror("依赖缺失", error_msg)
            logging.error(f"启动检查失败: 缺少依赖包 {missing_str}")
            return False
        else:
            logging.debug(self.lang_manager.get("all_dependencies_installed"))
            return True

    def install_dependencies(self, packages):
        """安装所需的依赖包"""
        for package in packages:
            logging.info(self.lang_manager.get("installing_dependency", package))
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logging.info(self.lang_manager.get("install_success", package))
            except subprocess.CalledProcessError as e:
                logging.error(self.lang_manager.get("install_failed", package, e))
                return False
        return True

    def _terminate_process_safely(self, process, timeout=5, process_name="子进程"):
        """安全终止进程：terminate → wait → kill
        
        Args:
            process: subprocess.Popen对象
            timeout: terminate后等待的超时时间（秒）
            process_name: 进程名称，用于日志
        
        Returns:
            bool: 是否成功终止
        """
        if not process or process.poll() is not None:
            # 进程不存在或已经结束
            return True
        
        try:
            # 步骤1: 尝试优雅终止
            logging.info(f"系统事件: 正在终止{process_name}...")
            process.terminate()
            
            # 步骤2: 等待进程结束
            try:
                exit_code = process.wait(timeout=timeout)
                logging.info(f"系统事件: {process_name}已终止，退出码: {exit_code}")
                return True
            except subprocess.TimeoutExpired:
                # 步骤3: 如果terminate失败，强制kill
                logging.warning(f"系统警告: {process_name}终止超时，正在强制杀死...")
                process.kill()
                try:
                    exit_code = process.wait(timeout=2)
                    logging.info(f"系统事件: {process_name}已被强制杀死，退出码: {exit_code}")
                    return True
                except subprocess.TimeoutExpired:
                    logging.error(f"系统错误: 无法终止{process_name}，进程可能成为僵尸进程")
                    return False
        except Exception as e:
            logging.error(f"系统错误: 终止{process_name}时发生异常: {e}", exc_info=True)
            return False

    def connect_server(self):
        """实际尝试连接服务器并测试WebSocket可用性"""
        ip = self.ip_var.get()
        port = self.port_var.get()
        ssl_enabled = self.use_ssl_var.get()

        # 禁用按钮，防止重复点击
        self.connect_button.config(state=tk.DISABLED)

        # 更新连接状态为未连接
        self._update_connection_indicator(False)

        # 获取启用/禁用文本
        ssl_status = (
            self.lang_manager.get("connect_enabled")
            if ssl_enabled
            else self.lang_manager.get("connect_disabled")
        )
        # 使用StatusManager显示连接中状态
        self.status_manager.set_stage(
            self.status_manager.STAGE_CONNECTING,
            f"{ip}:{port} (SSL: {ssl_status})"
        )
        logging.info(self.lang_manager.get("connecting_server", ip, port, ssl_status))
        logging.debug(self.lang_manager.get("connection_params", ip, port, ssl_enabled))

        # 在新线程中执行连接测试
        thread = threading.Thread(
            target=self._test_connection, args=(ip, port, ssl_enabled), daemon=True
        )
        thread.start()

    def _test_connection(self, ip, port, ssl_enabled):
        """在后台线程中测试WebSocket连接"""
        try:
            # 检查并安装依赖
            required_packages = ["websockets", "asyncio"]
            missing_packages = []

            for package in required_packages:
                try:
                    importlib.import_module(package)
                except ImportError:
                    missing_packages.append(package)

            if missing_packages:
                logging.warning(
                    self.lang_manager.get(
                        "dependency_check_before_connect", ", ".join(missing_packages)
                    )
                )
                logging.info(self.lang_manager.get("auto_installing"))
                if not self.install_dependencies(missing_packages):
                    logging.error(self.lang_manager.get("install_failed_cant_connect"))
                    # 使用StatusManager显示错误状态
                    self.status_manager.set_error(
                        self.lang_manager.get("error_msg", "依赖安装失败")
                    )
                    self.connect_button.config(state=tk.NORMAL)
                    return
                logging.info(self.lang_manager.get("install_completed_continue"))

                # 重新导入依赖（修复：移除局部importlib变量）
                for package in required_packages:
                    try:
                        importlib.import_module(package)
                    except ImportError:
                        pass

            # 导入websockets模块(必须在安装后导入)

            # 运行异步连接测试
            asyncio.run(self._async_test_connection(ip, port, ssl_enabled))

        except Exception as e:
            logging.error(
                self.lang_manager.get("connection_error", str(e)), exc_info=True
            )
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(self.lang_manager.get("error_msg", str(e)))
            self.connection_status = False
        finally:
            # 恢复按钮状态
            self.connect_button.config(state=tk.NORMAL)

    def _find_script_path(self):
        """查找simple_funasr_client.py脚本路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        target_script_name = "simple_funasr_client.py"

        # V3 优先：优先使用仓库根目录的 V3 脚本（包含协议适配层与 is_final 修复）
        # 兼容不同启动目录：向上最多探测 6 层父目录，寻找 src/python-gui-client/simple_funasr_client.py
        for _ in range(6):
            v3_candidate = os.path.join(
                current_dir, "src", "python-gui-client", target_script_name
            )
            if os.path.exists(v3_candidate):
                logging.info(f"使用 V3 识别脚本: {v3_candidate}")
                return v3_candidate
            current_dir = os.path.dirname(current_dir)

        # V2 兼容：回退到与 GUI 同目录的脚本
        local_candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), target_script_name)
        if os.path.exists(local_candidate):
            logging.info(f"使用本地识别脚本: {local_candidate}")
            return local_candidate

        # 旧逻辑兼容：samples 目录（作为后备）
        gui_dir = os.path.dirname(os.path.abspath(__file__))
        legacy_project_root = os.path.abspath(
            os.path.join(gui_dir, os.pardir, os.pardir)
        )
        samples_dir = os.path.join(legacy_project_root, "samples")
        samples_candidate = os.path.join(samples_dir, target_script_name)
        if os.path.exists(samples_candidate):
            logging.warning(
                f"系统警告: 在当前目录未找到 {target_script_name}，"
                f"但在 {samples_dir} 中找到。"
                "建议将脚本放在主程序同目录下。"
            )
            return samples_candidate

        return None

    def select_file(self):
        """打开文件对话框选择文件"""
        # 使用StatusManager显示选择文件状态
        self.status_manager.set_info(self.lang_manager.get("selecting_file"))
        # 注意：此处需要根据 funasr_wss_client.py 支持的格式调整 filetypes
        filetypes = (
            (
                self.lang_manager.get("audio_video_files"),
                "*.mp3 *.wma *.wav *.ogg *.ac3 *.m4a *.opus *.aac *.pcm "
                "*.mp4 *.wmv *.avi *.mov *.mkv *.mpg *.mpeg *.webm *.ts *.flv",
            ),
            (self.lang_manager.get("scp_files"), "*.scp"),
            (self.lang_manager.get("all_files"), "*.*"),
        )
        filepath = filedialog.askopenfilename(
            title=self.lang_manager.get("file_dialog_title"), filetypes=filetypes
        )
        if filepath:
            self.file_path_var.set(filepath)

            # 获取文件时长信息
            duration = self.time_manager.get_audio_duration(filepath)
            if duration is not None:
                duration_text = f"{int(duration//60)}分{int(duration % 60)}秒"
                # 使用StatusManager显示成功状态，3秒后自动恢复
                self.status_manager.set_success(
                    f"{self.lang_manager.get('file_selected')}: "
                    f"{os.path.basename(filepath)} (时长: {duration_text})",
                    temp_duration=3
                )
                logging.info(
                    f"文件选择: {filepath}, 时长: {duration:.1f}秒 ({duration_text})"
                )
            else:
                # 使用StatusManager显示成功状态，3秒后自动恢复
                self.status_manager.set_success(
                    f"{self.lang_manager.get('file_selected')}: "
                    f"{os.path.basename(filepath)}",
                    temp_duration=3
                )
                logging.info(f"文件选择: {filepath}, 无法获取时长信息")

            # 记录文件选择事件
            logging.debug(f"调试信息: 文件大小: {os.path.getsize(filepath)} 字节")
            logging.debug(f"调试信息: 文件类型: {os.path.splitext(filepath)[1]}")
        else:
            # 使用StatusManager显示警告状态
            self.status_manager.set_warning(self.lang_manager.get("no_file_selected"))
            logging.info(self.lang_manager.get("no_file_selected"))

    def select_hotword_file(self):
        """打开文件对话框选择热词文件"""
        filetypes = (
            (self.lang_manager.get("text_files"), "*.txt"),
            (self.lang_manager.get("all_files"), "*.*"),
        )
        filepath = filedialog.askopenfilename(
            title=self.lang_manager.get("select_hotword_dialog_title"),
            filetypes=filetypes
        )
        if filepath:
            self.hotword_path_var.set(filepath)
            # 使用StatusManager显示成功状态，3秒后自动恢复
            self.status_manager.set_success(
                f"{self.lang_manager.get('hotword_selected')}: {os.path.basename(filepath)}",
                temp_duration=3
            )
            logging.info(f"热词文件选择: {filepath}")
        else:
            logging.info("用户取消选择热词文件")

    def clear_hotword_file(self):
        """清除热词文件选择"""
        self.hotword_path_var.set("")
        # 使用StatusManager显示成功状态，3秒后自动恢复
        self.status_manager.set_success(self.lang_manager.get("hotword_cleared"), temp_duration=3)
        logging.info("热词文件已清除")

    def create_tooltip(self, widget, text):
        """为控件创建工具提示"""
        def on_enter(event):
            # 创建提示窗口
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)  # 移除窗口边框
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(
                tooltip,
                text=text,
                background="lightyellow",
                relief="solid",
                borderwidth=1,
                font=("Arial", 9),
                padx=5,
                pady=3
            )
            label.pack()
            
            # 将tooltip保存到widget，以便后续删除
            widget._tooltip = tooltip
        
        def on_leave(event):
            # 销毁提示窗口
            if hasattr(widget, '_tooltip'):
                widget._tooltip.destroy()
                del widget._tooltip
        
        # 绑定鼠标事件
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def start_recognition(self):
        """启动识别过程"""
        ip = self.ip_var.get()
        port = self.port_var.get()
        audio_in = self.file_path_var.get()

        if not audio_in:
            messagebox.showwarning(
                self.lang_manager.get("warning_title"),
                self.lang_manager.get("please_select_file"),
            )
            logging.error("用户错误: 未选择音频/视频文件")
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(self.lang_manager.get("please_select_file"))
            return

        if not ip or not port:
            messagebox.showwarning(
                self.lang_manager.get("warning_title"),
                self.lang_manager.get("please_connect_server"),
            )
            logging.error("用户错误: 服务器IP或端口未设置")
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(self.lang_manager.get("please_connect_server"))
            return

        # 如果未连接服务器，先尝试连接
        if not self.connection_status:
            logging.info("系统事件: 正在进行连接测试...")
            # 创建连接测试线程
            thread = threading.Thread(
                target=self._test_connection,
                args=(ip, port, self.use_ssl_var.get()),
                daemon=True,
            )
            thread.start()
            # 等待连接测试完成
            thread.join(timeout=6)  # 最多等待6秒
            logging.debug(
                f"调试信息: 连接测试线程完成, 连接状态: {self.connection_status}"
            )

            # 检查连接状态
            if not self.connection_status:
                logging.warning("系统警告: 服务器连接测试未成功，但仍将尝试识别")
                logging.warning(
                    "用户提示: 如果识别失败，请先使用'连接服务器'按钮测试连接"
                )

        # 计算转写时长
        wait_timeout, estimate_time = self.time_manager.calculate_transcribe_times(
            audio_in
        )

        # 记录时长计算结果
        if (
            self.time_manager.current_file_duration
            and self.time_manager.current_file_duration > 0
        ):
            duration_text = (
                f"{int(self.time_manager.current_file_duration//60)}分"
                f"{int(self.time_manager.current_file_duration % 60)}秒"
            )
            estimate_text = f"{estimate_time}秒" if estimate_time else "无法预估"
            logging.info(
                self.lang_manager.get(
                    "duration_calculation_with_time",
                    duration_text,
                    wait_timeout,
                    estimate_text,
                )
            )
        else:
            estimate_text = f"{estimate_time}秒" if estimate_time else "无法预估"
            logging.info(
                self.lang_manager.get(
                    "duration_calculation_without_time", wait_timeout, estimate_text
                )
            )

        # 禁用按钮，防止重复点击
        self.start_button.config(state=tk.DISABLED)
        self.select_button.config(state=tk.DISABLED)

        # 显示预估时长信息 - 使用StatusManager设置准备阶段
        if estimate_time:
            estimate_text = (
                f"{int(estimate_time//60)}分{int(estimate_time % 60)}秒"
                if estimate_time >= 60
                else f"{estimate_time}秒"
            )
            # 使用StatusManager显示准备阶段
            self.status_manager.set_stage(
                self.status_manager.STAGE_PREPARING,
                f"预计{estimate_text}"
            )
        else:
            # 无预估时显示准备阶段
            self.status_manager.set_stage(self.status_manager.STAGE_PREPARING)

        logging.info(self.lang_manager.get("starting_recognition", audio_in))
        logging.debug(
            self.lang_manager.get(
                "recognition_params", ip, port, audio_in, self.use_itn_var.get()
            )
        )

        # 在新线程中运行识别脚本
        thread = threading.Thread(
            target=self._run_script,
            args=(ip, port, audio_in, wait_timeout, estimate_time),
            daemon=True,
        )
        thread.start()

    def _run_script(self, ip, port, audio_in, wait_timeout=600, estimate_time=60):
        """在新线程中运行 simple_funasr_client.py 脚本。"""
        # 构造要传递给子进程的参数列表
        # ... (参数构造部分保持不变) ...
        script_path = self._find_script_path()
        if not script_path:
            logging.error(self.lang_manager.get("script_not_found"))
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(self.lang_manager.get("script_not_found_status"))
            return

        # 设置输出目录到 dev/output 文件夹（遵循架构设计文档）
        results_dir = self.output_dir
        os.makedirs(results_dir, exist_ok=True)

        args = [
            sys.executable,  # 使用当前 Python 解释器
            script_path,
            "--host",
            ip,
            "--port",
            str(port),
            "--audio_in",
            audio_in,
            "--output_dir",
            results_dir,  # 添加输出目录参数
            "--transcribe_timeout",
            str(wait_timeout),  # 添加动态超时参数
            # 根据 Checkbutton 状态添加 --no-itn 或 --no-ssl
        ]
        if self.use_itn_var.get() == 0:
            args.append("--no-itn")
        if self.use_ssl_var.get() == 0:
            args.append("--no-ssl")
        
        # 添加热词文件参数（如果已选择）
        hotword_path = self.hotword_path_var.get()
        if hotword_path and os.path.exists(hotword_path):
            args.extend(["--hotword", hotword_path])
            logging.info(f"使用热词文件: {hotword_path}")

        # 清空之前的识别结果区域（但保留系统日志）
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)  # 清空结果区域
        self.result_text.configure(state="disabled")

        # 日志区域不清空，保留之前的系统日志
        self.log_text.configure(state="normal")
        # self.log_text.delete('1.0', tk.END) # 取消启动时清空，不清空之前的系统日志
        self.log_text.configure(state="disabled")
        logging.info(self.lang_manager.get("task_start", os.path.basename(audio_in)))
        logging.info(self.lang_manager.get("results_save_location", results_dir))
        self.start_button.config(state=tk.DISABLED)  # 禁用开始按钮

        # 进度倒计时相关变量
        transcribe_start_time = None  # 转写开始时间
        upload_completed = False  # 上传是否完成
        task_completed = False  # 任务是否完成
        process = None  # 子进程对象

        last_message_time = time.time()  # 初始化上次收到消息的时间

        # 倒计时更新函数
        def update_countdown():
            # 如果任务已完成，停止倒计时
            if task_completed:
                return

            if upload_completed and transcribe_start_time:
                # 转写阶段，显示倒计时
                elapsed = time.time() - transcribe_start_time

                if estimate_time:
                    # 有预估时长的情况
                    remaining = max(0, estimate_time - elapsed)

                    if remaining > 0:
                        remaining_text = (
                            f"{int(remaining//60)}分{int(remaining % 60)}秒"
                            if remaining >= 60
                            else f"{int(remaining)}秒"
                        )
                        progress_percent = min(
                            100, int((elapsed / estimate_time) * 100)
                        )
                        # 使用StatusManager显示处理进度
                        detail = f"{progress_percent}% 剩余{remaining_text}"
                        self.status_manager.set_stage(
                            self.status_manager.STAGE_PROCESSING,
                            detail
                        )
                    else:
                        # 预估时间已过，使用StatusManager显示处理中状态（警告）
                        elapsed_text = (
                            f"{int(elapsed//60)}分{int(elapsed % 60)}秒"
                            if elapsed >= 60
                            else f"{int(elapsed)}秒"
                        )
                        self.status_manager.set_warning(
                            f"⏱ 处理中... 已用时{elapsed_text}（超出预估）"
                        )
                else:
                    # 无预估时长的情况，使用StatusManager显示处理中状态
                    elapsed_text = (
                        f"{int(elapsed//60)}分{int(elapsed % 60)}秒"
                        if elapsed >= 60
                        else f"{int(elapsed)}秒"
                    )
                    self.status_manager.set_stage(
                        self.status_manager.STAGE_PROCESSING,
                        f"已用时{elapsed_text}"
                    )

                # 继续更新倒计时
                self.after(1000, update_countdown)
            elif not upload_completed:
                # 上传阶段，使用StatusManager显示上传状态
                self.status_manager.set_stage(
                    self.status_manager.STAGE_UPLOADING,
                    os.path.basename(audio_in)
                )
                self.after(1000, update_countdown)

        def run_in_thread():
            # 允许修改外部变量
            nonlocal transcribe_start_time, upload_completed, task_completed, process, last_message_time
            # 添加变量以跟踪上次记录的上传进度
            last_logged_progress = -5  # 初始值设为-5，确保0%会被打印
            # 添加变量跟踪是否收到了有效的识别结果
            received_valid_result = False
            # 记录是否明确写入了结果文件（来自子进程提示）
            result_file_written = False

            try:
                logging.debug(f"调试信息: 正在执行命令: {' '.join(args)}")
                # 记录进程启动时间，用于后续判断结果文件是否为本次运行生成
                process_start_time = time.time()
                # 使用 Popen 启动子进程，捕获 stdout 和 stderr
                process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )

                # 并发读取stderr，将错误即时写入日志
                def _read_stderr_stream(stream):
                    try:
                        for err_line in iter(stream.readline, ""):
                            if not err_line:
                                break
                            logging.error(f"{self.lang_manager.get('subprocess_error')}\n{err_line.strip()}")
                    except Exception:
                        pass

                stderr_thread = threading.Thread(
                    target=_read_stderr_stream, args=(process.stderr,), daemon=True
                )
                stderr_thread.start()

                # 实时读取 stdout
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        stripped_line = line.strip()
                        # 更新最近消息时间，供通信超时判定
                        last_message_time = time.time()

                        # 检查是否收到了有效的识别结果
                        if (
                            "识别结果:" in stripped_line and len(stripped_line) > 20
                        ):  # 确保不是空结果
                            received_valid_result = True
                            # 提取识别结果文本并显示在结果区域
                            result_text = stripped_line.replace("识别结果:", "").strip()
                            self.after(0, self._display_recognition_result, result_text)
                            logging.info(
                                f"{self.lang_manager.get('server_response')}: "
                                f"{stripped_line}"
                            )
                        elif stripped_line.startswith(
                            "[DEBUG]"
                        ) or stripped_line.startswith(
                            self.lang_manager.get("log_tag_debug")
                        ):
                            # 统一使用翻译后的DEBUG标签
                            actual_message = (
                                stripped_line.replace("[DEBUG]", "")
                                .replace(self.lang_manager.get("log_tag_debug"), "")
                                .strip()
                            )
                            if "使用SSL连接" in actual_message:
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: "
                                    f"{self.lang_manager.get('log_tag_debug')} "
                                    f"{self.lang_manager.get('log_use_ssl_connection')}"
                                )
                            elif actual_message.startswith("连接到 wss://"):
                                parts = actual_message.replace(
                                    "连接到 wss://", ""
                                ).split(":")
                                if len(parts) == 2:
                                    wss_msg = self.lang_manager.get(
                                        "log_connected_to_wss", parts[0], parts[1]
                                    )
                                    logging.debug(
                                        f"{self.lang_manager.get('client_event')}: "
                                        f"{self.lang_manager.get('log_tag_debug')} "
                                        f"{wss_msg}"
                                    )
                                else:
                                    logging.debug(
                                        f"{self.lang_manager.get('client_debug')}: "
                                        f"{actual_message}"
                                    )
                            elif "处理文件数:" in actual_message:
                                count = actual_message.split(":")[1].strip()
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: "
                                    f"{self.lang_manager.get('log_tag_debug')} "
                                    f"{self.lang_manager.get('log_processed_file_count')}: "
                                    f"{count}"
                                )
                            elif "处理文件:" in actual_message:
                                f_path = actual_message.split(":")[1].strip()
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: "
                                    f"{self.lang_manager.get('log_tag_debug')} "
                                    f"{self.lang_manager.get('log_processing_file_path')}: {f_path}"
                                )
                            elif "文件大小:" in actual_message:
                                f_size = actual_message.split(":")[1].strip()
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('log_tag_debug')} {self.lang_manager.get('log_file_size_simple')}: {f_size}"
                                )
                            elif "已读取WAV文件, 采样率:" in actual_message:
                                parts = actual_message.replace(
                                    "已读取WAV文件, 采样率:", ""
                                ).split(", 文件大小:")
                                rate = parts[0].strip()
                                size = parts[1].strip() if len(parts) > 1 else "N/A"
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: "
                                    f"{self.lang_manager.get('log_tag_debug')} "
                                    f"{self.lang_manager.get('log_read_wav_file')}, "
                                    f"{self.lang_manager.get('log_sample_rate')}: {rate}, "
                                    f"{self.lang_manager.get('log_file_size_simple')}: {size}"
                                )
                            elif "分块数:" in actual_message:
                                parts = actual_message.replace("分块数:", "").split(
                                    ", 每块大小:"
                                )
                                count = parts[0].strip()
                                size_info = (
                                    parts[1].strip() if len(parts) > 1 else "N/A"
                                )
                                note = (
                                    self.lang_manager.get("log_offline_stride_note")
                                    if "offline模式" in actual_message
                                    else ""
                                )
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: "
                                    f"{self.lang_manager.get('log_tag_debug')} "
                                    f"{self.lang_manager.get('log_chunk_count')}: {count}, "
                                    f"{self.lang_manager.get('log_chunk_size_info')}: {size_info} {note}"
                                )
                            elif "等待服务器处理完成" in actual_message:
                                logging.debug(
                                    f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('log_tag_debug')} {self.lang_manager.get('waiting_server')}..."
                                )
                            else:
                                logging.debug(
                                    f"{self.lang_manager.get('client_debug')}: {actual_message}"
                                )
                        elif stripped_line.startswith(
                            "[指令]"
                        ) or stripped_line.startswith(
                            self.lang_manager.get("log_tag_instruction")
                        ):
                            actual_message = (
                                stripped_line.replace("[指令]", "")
                                .replace(
                                    self.lang_manager.get("log_tag_instruction"), ""
                                )
                                .strip()
                            )
                            if "发送WebSocket:" in actual_message:
                                config_part = actual_message.split("发送WebSocket:", 1)[
                                    1
                                ].strip()
                                logging.info(
                                    f"{self.lang_manager.get('client_event')}: "
                                    f"{self.lang_manager.get('log_tag_instruction')} "
                                    f"{self.lang_manager.get('log_sent_websocket_config', config_part)}"
                                )
                            else:
                                logging.info(
                                    f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('log_tag_instruction')} {actual_message}"
                                )
                        elif "上传进度" in stripped_line:
                            try:
                                import re

                                progress_match = re.search(r"(\d+)%", stripped_line)
                                if progress_match:
                                    progress_value = int(progress_match.group(1))
                                    # 确保0%和100%会被打印，且步进为5%
                                    if (
                                        progress_value == 0
                                        or progress_value == 100
                                        or (
                                            progress_value % 5 == 0
                                            and progress_value > last_logged_progress
                                        )
                                    ):
                                        progress_text = f"{progress_value}%"
                                        logging.info(
                                            f"{self.lang_manager.get('server_response')}: "
                                            f"{self.lang_manager.get('upload_progress')}: {progress_text}"
                                        )
                                        last_logged_progress = (
                                            progress_value
                                            if progress_value != 100
                                            else last_logged_progress
                                        )  # 避免100%后阻止后续可能的其他类型日志打印

                                    # 检测上传完成，开始转写倒计时
                                    if progress_value == 100 and not upload_completed:
                                        upload_completed = True
                                        transcribe_start_time = time.time()
                                        logging.info("转写阶段开始，启动进度倒计时")
                                else:
                                    # 旧的提取逻辑作为后备
                                    if ":" in stripped_line:
                                        progress = stripped_line.split(":", 1)[
                                            1
                                        ].strip()
                                    else:
                                        progress = stripped_line
                                    logging.info(
                                        f"{self.lang_manager.get('server_response')}: {self.lang_manager.get('upload_progress')}: {progress}"
                                    )
                            except Exception:
                                logging.info(
                                    f"{self.lang_manager.get('server_response')}: {stripped_line}"
                                )
                        elif "等待接收消息..." in stripped_line:
                            logging.info(
                                f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('debug_tag')} {self.lang_manager.get('log_waiting_for_message')}"
                            )
                        elif "创建结果文件" in stripped_line:
                            # 处理创建结果文件消息
                            logging.info(
                                f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('debug_tag')} {self.lang_manager.get('create_result_file')}..."
                            )
                        elif "结果文件已完成" in stripped_line:
                            # 处理结果文件完成消息
                            logging.info(
                                f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('debug_tag')} {self.lang_manager.get('result_file_created')}"
                            )
                        elif "JSON结果文件已写入并关闭" in stripped_line:
                            # 处理JSON结果文件完成消息
                            logging.info(
                                f"{self.lang_manager.get('client_event')}: {self.lang_manager.get('debug_tag')} {self.lang_manager.get('json_result_file_created')}"
                            )
                            result_file_written = True
                        elif (
                            "Namespace" in stripped_line or "命名空间" in stripped_line
                        ):
                            # 处理命名空间信息 (包含一些不需要翻译的参数信息)
                            logging.info(
                                f"{self.lang_manager.get('server_response')}: {self.lang_manager.get('namespace_info')}: {stripped_line.split('命名空间')[-1] if '命名空间' in stripped_line else stripped_line.split('Namespace')[-1]}"
                            )
                        elif "处理完成" in stripped_line:
                            # 处理完成消息
                            logging.info(
                                f"{self.lang_manager.get('server_response')}: {self.lang_manager.get('processing_completed')}"
                            )
                        elif not stripped_line.startswith("["):
                            # 其他未分类的输出
                            logging.info(
                                f"{self.lang_manager.get('client_event')}: {stripped_line}"
                            )

                # 等待进程结束并获取返回码
                return_code = process.wait()

                # 严格化成功判定：必须同时满足以下条件
                # 1. 退出码为0（进程正常退出）
                # 2. 有有效的识别结果（收到识别文本 或 有有效的结果文件）
                def _exists_valid_result_file() -> bool:
                    """检查是否存在有效的结果文件（非空且有实际内容）"""
                    try:
                        base_name = os.path.splitext(os.path.basename(audio_in))[0]
                        for fname in os.listdir(results_dir):
                            if fname.startswith(base_name + ".") and fname.endswith(".json"):
                                fpath = os.path.join(results_dir, fname)
                                file_size = os.path.getsize(fpath)
                                file_mtime = os.path.getmtime(fpath)
                                
                                # 文件必须：1) 大于100字节（排除空文件/占位文件）
                                #           2) 修改时间晚于进程启动时间
                                if file_size > 100 and file_mtime >= process_start_time:
                                    logging.info(f"检测到有效结果文件: {fname} ({file_size} 字节)")
                                    return True
                                elif file_mtime >= process_start_time:
                                    logging.warning(f"结果文件过小: {fname} ({file_size} 字节)，可能不完整")
                        return False
                    except Exception as e:
                        logging.error(f"检查结果文件时出错: {e}")
                        return False

                # 成功判定条件：退出码=0 且 (有识别结果 或 有有效结果文件)
                success_by_artifact = result_file_written or _exists_valid_result_file()
                has_valid_result = received_valid_result or success_by_artifact
                
                if return_code == 0 and has_valid_result:
                    logging.info(
                        self.lang_manager.get(
                            "task_success", os.path.basename(audio_in)
                        )
                    )
                    task_completed = True
                    # 使用StatusManager显示完成阶段
                    self.after(
                        0,
                        lambda: self.status_manager.set_stage(self.status_manager.STAGE_COMPLETED)
                    )
                else:
                    # 失败原因分析
                    if return_code != 0:
                        reason = f"进程异常退出(退出码:{return_code})"
                    elif not has_valid_result:
                        reason = "未收到有效识别结果"
                    else:
                        reason = "未知原因"
                    
                    logging.error(
                        f"任务失败: 文件 {os.path.basename(audio_in)} 识别失败 - {reason}"
                    )
                    task_completed = True  # 即使失败也标记任务完成，停止倒计时
                    # 使用StatusManager显示错误状态
                    self.after(
                        0,
                        lambda r=reason: self.status_manager.set_error(
                            f"识别失败: {r}"
                        )
                    )
                    # Display error in a popup
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            self.lang_manager.get("recognition_error_title"),
                            self.lang_manager.get("file_processing_error", self.lang_manager.get("unknown_error")),
                        ),
                    )

            except FileNotFoundError:
                logging.error(
                    f"{self.lang_manager.get('python_not_found', sys.executable, script_path)}"
                )
                task_completed = True  # 标记任务完成，停止倒计时
                # 使用StatusManager显示错误状态
                self.after(
                    0,
                    lambda: self.status_manager.set_error(
                        self.lang_manager.get("script_not_found_error")
                    )
                )
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        self.lang_manager.get("startup_error_title"),
                        self.lang_manager.get("python_env_check"),
                    ),
                )
            except Exception as e:
                error_details = traceback.format_exc()
                logging.error(
                    f"{self.lang_manager.get('system_error')}: {self.lang_manager.get('unexpected_error_msg', str(e), error_details)}"
                )
                task_completed = True  # 标记任务完成，停止倒计时
                # 使用StatusManager显示错误状态
                error_msg = str(e)
                self.after(
                    0,
                    lambda: self.status_manager.set_error(
                        self.lang_manager.get("running_unexpected_error", error_msg)
                    )
                )
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        self.lang_manager.get("unexpected_error_title"),
                        self.lang_manager.get("unexpected_error_popup", error_msg),
                    ),
                )
            finally:
                # 确保无论成功或失败，都重新启用按钮
                self.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                self.after(
                    0, lambda: self.select_button.config(state=tk.NORMAL)
                )  # 恢复文件选择按钮
                # 确保进程被终止（如果它仍在运行）
                if process and process.poll() is None:
                    self._terminate_process_safely(process, timeout=5, process_name="识别进程")

        # 启动超时监控 - 使用动态计算的wait_timeout（修复：使用绝对时间判断）
        def check_timeout():
            # 如果任务已完成，停止超时检查
            if task_completed:
                return
            
            current_time = time.time()

            # 检查是否超过系统等待超时时间（使用绝对时间判断）
            if transcribe_start_time:
                elapsed = current_time - transcribe_start_time
                
                if elapsed > wait_timeout:
                    if process and process.poll() is None:
                        logging.warning(
                            f"转写超时: 已用时{elapsed:.0f}秒，超过设定{wait_timeout}秒"
                        )
                        self._terminate_process_safely(process, timeout=5, process_name="识别进程(超时)")
                        # 使用StatusManager显示错误状态
                        self.after(
                            0,
                            lambda: self.status_manager.set_error(f"转写超时 (超过{wait_timeout}秒)")
                        )
                        self.after(
                            0,
                            lambda: messagebox.showerror(
                                self.lang_manager.get("transcription_timeout"),
                                self.lang_manager.get(
                                    "transcription_timeout_msg", wait_timeout
                                ),
                            ),
                        )
                        self.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                        return  # 超时后停止调度
            
            # 检查通信超时（基于最后消息时间）
            comm_timeout = max(600, wait_timeout // 2)  # 通信超时=max(10分钟, 系统超时的一半)
            if (current_time - last_message_time) > comm_timeout:
                if process and process.poll() is None:
                    elapsed_comm = current_time - last_message_time
                    logging.warning(
                        f"通信超时: 距上次消息已{elapsed_comm:.0f}秒，超过设定{comm_timeout}秒"
                    )
                    self._terminate_process_safely(process, timeout=5, process_name="识别进程(通信超时)")
                    # 使用StatusManager显示错误状态
                    self.after(
                        0,
                        lambda: self.status_manager.set_error(
                            f"{self.lang_manager.get('communication_timeout')}"
                        )
                    )
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            self.lang_manager.get("communication_timeout"),
                            self.lang_manager.get(
                                "communication_timeout_msg", comm_timeout
                            ),
                        ),
                    )
                    self.after(0, lambda: self.start_button.config(state=tk.NORMAL))
                    return  # 超时后停止调度
            
            # 继续监控（无论进程状态如何，都继续调度，由task_completed控制停止）
            self.after(1000, check_timeout)

        # 在新线程中运行脚本
        thread = threading.Thread(target=run_in_thread)
        thread.daemon = True  # 设置为守护线程，以便主程序退出时子线程也退出
        thread.start()

        # 启动倒计时更新和超时检查
        self.after(1000, update_countdown)  # 启动倒计时更新
        self.after(1000, check_timeout)  # 启动超时检查

    async def _async_test_connection(self, ip, port, ssl_enabled):
        """异步测试WebSocket连接"""
        import websockets

        try:
            # 创建SSL上下文 (直接从funasr_wss_client.py采用相同代码)
            if ssl_enabled == 1:
                # 修复: 使用推荐的SSL上下文创建方法
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                uri = f"wss://{ip}:{port}"
            else:
                uri = f"ws://{ip}:{port}"
                ssl_context = None

            logging.info(self.lang_manager.get("trying_websocket_connection", uri))
            logging.debug(f"调试信息: SSL上下文: {ssl_context is not None}")

            # 设置超时时间（从配置读取）
            timeout = int(getattr(self, "connection_test_timeout", 10))
            logging.debug(f"调试信息: 连接超时设置: {timeout}秒")

            # 使用与funasr_wss_client.py相同的连接参数
            try:
                # 修复：先创建连接对象，然后用await等待连接完成
                connection = websockets.connect(
                    uri,
                    subprotocols=["binary"],
                    ping_interval=None,
                    ssl=ssl_context,
                    proxy=None,  # 显式禁用代理
                )
                logging.debug("调试信息: 创建WebSocket连接对象")

                # 使用wait_for添加超时，但不作为上下文管理器
                websocket = await asyncio.wait_for(connection, timeout=timeout)
                logging.debug("调试信息: WebSocket连接已建立")

                # 使用websocket作为上下文管理器
                async with websocket:
                    # 发送简单的ping/初始化消息检查连接
                    try:
                        # 尝试使用与simple_funasr_client更一致的初始化消息
                        message = json.dumps(
                            {
                                "mode": "offline",
                                "audio_fs": 16000,
                                "wav_name": "ping",
                                "wav_format": "others",
                                "is_speaking": True,
                                "hotwords": "",
                                "itn": True,
                            }
                        )
                        await websocket.send(message)
                        logging.info(self.lang_manager.get("websocket_message_sent"))
                        logging.debug(f"调试信息: 发送的消息: {message}")

                        # 收紧判定：必须在超时内收到任意响应才算成功
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            logging.info(self.lang_manager.get("real_time_websocket_connect"))
                            # 根据官方协议，部分服务在首包不回复，这里视为"基础连通成功但无响应"，点亮已连接，并提示
                            # 使用StatusManager显示成功状态（主线程调度）
                            self.status_bar.after(0, lambda: self.status_manager.set_success(
                                self.lang_manager.get("real_time_websocket_connect")
                            ))
                            self.status_bar.after(0, lambda: self._update_connection_indicator(True))
                            return
                        logging.info(
                            self.lang_manager.get(
                                "websocket_response_received", response
                            )
                        )

                        logging.info(
                            self.lang_manager.get("websocket_connection_test_success")
                        )
                        # 使用StatusManager显示成功状态（主线程调度）
                        self.status_bar.after(0, lambda: self.status_manager.set_success(
                            self.lang_manager.get("connection_success", f"{ip}:{port}")
                        ))
                        # 更新连接状态为已连接
                        self.status_bar.after(0, lambda: self._update_connection_indicator(True))

                    except websockets.exceptions.ConnectionClosedOK:
                        # 服务器主动关闭连接，不再直接记为成功（缺少有效响应）
                        logging.warning("系统警告: 连接建立后被服务器关闭，未收到有效响应")
                        # 使用StatusManager显示警告状态（主线程调度）
                        self.status_bar.after(0, lambda: self.status_manager.set_warning("连接建立但无响应"))
                        self.status_bar.after(0, lambda: self._update_connection_indicator(False))

                    except websockets.exceptions.ConnectionClosedError as e:
                        logging.warning(f"系统警告: WebSocket连接被中断: {e}")
                        logging.warning(
                            "系统警告: 服务器可能支持WebSocket但不接受当前消息格式"
                        )
                        # 这种情况仍然视为连接部分成功
                        logging.info(
                            "用户提示: WebSocket连接基本成功，但服务器可能期望不同的消息格式"
                        )
                        # 使用StatusManager显示警告状态（主线程调度）
                        self.status_bar.after(0, lambda ip=ip, port=port: self.status_manager.set_warning(f"连接部分成功: {ip}:{port}"))
                        # 更新连接状态为已连接，但用户应该注意可能有问题
                        self.status_bar.after(0, lambda: self._update_connection_indicator(True))

                    except Exception as e:
                        logging.error(
                            f"系统错误: WebSocket消息发送/接收错误: {e}", exc_info=True
                        )
                        # 通信有问题，视为失败 - 使用StatusManager显示错误状态（主线程调度）
                        self.status_bar.after(0, lambda ip=ip, port=port: self.status_manager.set_error(f"连接失败: 通信异常 {ip}:{port}"))
                        self.status_bar.after(0, lambda: self._update_connection_indicator(False))

            except asyncio.TimeoutError:
                logging.error(f"系统错误: 连接 {uri} 超时，服务器无响应")
                # 使用StatusManager显示错误状态（主线程调度）
                self.status_bar.after(0, lambda ip=ip, port=port: self.status_manager.set_error(f"连接超时: {ip}:{port}"))
                # 更新连接状态为未连接
                self.status_bar.after(0, lambda: self._update_connection_indicator(False))

            except websockets.exceptions.WebSocketException as e:
                logging.error(f"系统错误: WebSocket错误: {e}", exc_info=True)

                # 根据不同错误类型提供具体建议
                if isinstance(e, websockets.exceptions.InvalidStatusCode):
                    status_code = getattr(e, "status_code", "未知")
                    logging.error(
                        f"系统错误: 收到HTTP状态码 {status_code}，但不是WebSocket握手"
                    )
                    logging.warning(
                        "用户提示: 服务器可能不支持WebSocket或在该端口上运行了其他服务"
                    )

                elif isinstance(e, websockets.exceptions.InvalidMessage):
                    logging.error("系统错误: 收到无效的WebSocket握手消息")
                    # 如果非SSL模式失败，建议尝试SSL模式
                    if ssl_enabled == 0:
                        logging.warning("用户提示: 建议尝试启用SSL选项后重新连接")

                # 使用StatusManager显示错误状态（主线程调度）
                self.status_bar.after(0, lambda: self.status_manager.set_error("连接失败: WebSocket错误"))
                # 更新连接状态为未连接
                self.status_bar.after(0, lambda: self._update_connection_indicator(False))

        except ConnectionRefusedError:
            logging.error(
                f"系统错误: 连接到 {ip}:{port} 被拒绝。服务器可能未启动或端口错误。"
            )
            # 使用StatusManager显示错误状态（主线程调度）
            self.status_bar.after(0, lambda ip=ip, port=port: self.status_manager.set_error(f"连接被拒绝: {ip}:{port}"))
            # 更新连接状态为未连接
            self.status_bar.after(0, lambda: self._update_connection_indicator(False))

        except Exception as e:
            logging.error(f"系统错误: 测试连接时发生未捕获的异常: {e}", exc_info=True)

            # 提供特定错误的建议
            if "ssl" in str(e).lower():
                logging.warning("用户提示: 如果启用了SSL，请尝试禁用SSL选项后重试")
                logging.warning("用户提示: 或者确认服务器是否正确配置了SSL证书")
            elif "connection" in str(e).lower():
                logging.warning(
                    "用户提示: 请检查服务器是否正在运行，以及IP和端口是否正确"
                )
                logging.warning(
                    "用户提示: 可尝试的端口: 离线识别(10095)，实时识别(10096)，标点(10097)"
                )

            # 使用StatusManager显示错误状态（主线程调度）
            error_type = type(e).__name__
            self.status_bar.after(0, lambda error_type=error_type: self.status_manager.set_error(f"连接错误: {error_type}"))
            # 更新连接状态为未连接
            self.status_bar.after(0, lambda: self._update_connection_indicator(False))

    def _update_connection_indicator(self, connected=False):
        """更新连接状态指示器"""
        self.connection_status = connected
        if connected:
            self.connection_indicator.config(
                text=self.lang_manager.get("connected"), foreground="green"
            )
        else:
            self.connection_indicator.config(
                text=self.lang_manager.get("not_connected"), foreground="red"
            )

    def open_log_file(self):
        """打开日志文件所在的目录或直接打开日志文件"""
        log_file_path = self.log_file
        log_dir = os.path.dirname(log_file_path)
        logging.info(f"用户操作: 尝试打开日志文件: {log_file_path}")
        try:
            if sys.platform == "win32":
                # 在 Windows 上，尝试直接打开文件，如果失败则打开目录
                try:
                    os.startfile(log_file_path)
                    logging.info(
                        f"系统事件: 使用 os.startfile 打开日志文件 {log_file_path}"
                    )
                except OSError:
                    logging.warning(
                        f"系统警告: 无法直接打开日志文件 {log_file_path}，尝试打开目录 {log_dir}"
                    )
                    os.startfile(log_dir)
                    logging.info(f"系统事件: 使用 os.startfile 打开日志目录 {log_dir}")
            elif sys.platform == "darwin":  # macOS
                try:
                    subprocess.run(
                        ["open", "-R", log_file_path], check=True
                    )  # 在 Finder 中显示文件
                    logging.info(
                        f"系统事件: 使用 'open -R' 在 Finder 中显示日志文件 {log_file_path}"
                    )
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    logging.error(
                        f"系统错误: 无法在 Finder 中显示日志文件，尝试打开目录: {e}"
                    )
                    subprocess.run(["open", log_dir], check=True)  # 打开目录
                    logging.info(f"系统事件: 使用 'open' 打开日志目录 {log_dir}")
            else:  # Linux and other Unix-like
                try:
                    # 尝试使用 xdg-open 打开目录，更通用
                    subprocess.run(["xdg-open", log_dir], check=True)
                    logging.info(f"系统事件: 使用 'xdg-open' 打开日志目录 {log_dir}")
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    logging.error(
                        f"系统错误: 无法使用 xdg-open 打开日志目录 {log_dir}: {e}"
                    )
                    messagebox.showwarning(
                        "无法打开", f"无法自动打开日志目录。请手动导航至: {log_dir}"
                    )
        except Exception as e:
            logging.error(f"系统错误: 打开日志文件/目录时发生错误: {e}", exc_info=True)
            messagebox.showerror("错误", f"无法打开日志文件或目录: {e}")

    def open_results_folder(self):
        """打开结果目录"""
        results_dir = self.output_dir
        logging.info(f"用户操作: 尝试打开结果目录: {results_dir}")
        try:
            if sys.platform == "win32":
                # 在 Windows 上，尝试直接打开文件夹，如果失败则打开目录
                try:
                    os.startfile(results_dir)
                    logging.info(
                        f"系统事件: 使用 os.startfile 打开结果目录 {results_dir}"
                    )
                except OSError:
                    logging.warning(
                        f"系统警告: 无法直接打开结果目录 {results_dir}，尝试打开目录 {os.path.dirname(results_dir)}"
                    )
                    os.startfile(os.path.dirname(results_dir))
                    logging.info(
                        f"系统事件: 使用 os.startfile 打开结果目录父目录 {os.path.dirname(results_dir)}"
                    )
            elif sys.platform == "darwin":  # macOS
                try:
                    subprocess.run(
                        ["open", "-R", results_dir], check=True
                    )  # 在 Finder 中显示文件夹
                    logging.info(
                        f"系统事件: 使用 'open -R' 在 Finder 中显示结果目录 {results_dir}"
                    )
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    logging.error(
                        f"系统错误: 无法在 Finder 中显示结果目录，尝试打开目录: {e}"
                    )
                    subprocess.run(
                        ["open", os.path.dirname(results_dir)], check=True
                    )  # 打开目录
                    logging.info(
                        f"系统事件: 使用 'open' 打开结果目录父目录 {os.path.dirname(results_dir)}"
                    )
            else:  # Linux and other Unix-like
                try:
                    # 尝试使用 xdg-open 打开目录，更通用
                    subprocess.run(["xdg-open", results_dir], check=True)
                    logging.info(
                        f"系统事件: 使用 'xdg-open' 打开结果目录 {results_dir}"
                    )
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    logging.error(
                        f"系统错误: 无法使用 xdg-open 打开结果目录 {results_dir}: {e}"
                    )
                    messagebox.showwarning(
                        "无法打开", f"无法自动打开结果目录。请手动导航至: {results_dir}"
                    )
        except Exception as e:
            logging.error(f"系统错误: 打开结果目录时发生错误: {e}", exc_info=True)
            messagebox.showerror("错误", f"无法打开结果目录: {e}")

    def start_speed_test(self):
        """启动速度测试过程"""
        if self.speed_test_running:
            logging.warning(self.lang_manager.get("user_warn_speed_test_running"))
            # 使用StatusManager显示警告状态
            self.status_manager.set_warning(self.lang_manager.get("user_warn_speed_test_running"))
            return

        # 检查服务器连接
        ip = self.ip_var.get()
        port = self.port_var.get()

        if not ip or not port:
            logging.error(
                "用户错误: 服务器IP或端口未设置"
            )  # 这个日志用户一般看不到，但保留
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(
                self.lang_manager.get(
                    "error_msg", self.lang_manager.get("please_connect_server")
                )
            )  # 更具体的错误提示
            messagebox.showerror(
                self.lang_manager.get("error_title"),
                self.lang_manager.get("please_connect_server"),
            )
            return

        # 如果未连接服务器，先尝试连接
        if not self.connection_status:
            logging.info("系统事件: 正在进行连接测试...")
            # 创建连接测试线程
            thread = threading.Thread(
                target=self._test_connection,
                args=(ip, port, self.use_ssl_var.get()),
                daemon=True,
            )
            thread.start()
            # 等待连接测试完成
            thread.join(timeout=6)  # 最多等待6秒

            # 检查连接状态
            if not self.connection_status:
                logging.warning(
                    "系统警告: 服务器连接测试未成功，无法进行速度测试"
                )  # 日志保留
                # 使用StatusManager显示错误状态
                self.status_manager.set_error(
                    self.lang_manager.get(
                        "error_msg", self.lang_manager.get("please_connect_server")
                    )
                )  # 状态栏提示连接错误
                messagebox.showerror(
                    self.lang_manager.get("connection_error", ""),
                    self.lang_manager.get("please_connect_server"),
                )  # 弹窗提示连接错误
                return

        # 初始化测试相关变量
        self.speed_test_running = True
        self.test_file_index = 0
        self.test_files = []
        self.upload_times = []
        self.transcribe_times = []
        self.file_sizes = []

        # 设置测试状态
        self.current_speed_test_status_key_and_args = ("test_preparing", [])
        self.speed_test_status_var.set(
            self.lang_manager.get(*self.current_speed_test_status_key_and_args)
        )
        # 使用StatusManager显示准备状态
        self.status_manager.set_stage(
            self.status_manager.STAGE_PREPARING,
            "速度测试"
        )
        self.speed_test_button.config(state=tk.DISABLED)

        # 查找测试文件 - 使用仓库根目录下的resources/demo目录
        repo_root = os.path.abspath(os.path.join(self.project_root, os.pardir))
        demo_dir = os.path.join(repo_root, "resources", "demo")
        mp4_file = os.path.join(demo_dir, "tv-report-1.mp4")
        wav_file = os.path.join(demo_dir, "tv-report-1.wav")

        if not os.path.exists(mp4_file) or not os.path.exists(wav_file):
            logging.error(
                f"系统错误: 测试文件不存在，请确保 {demo_dir} 目录下有 tv-report-1.mp4 和 tv-report-1.wav 文件"
            )  # 日志保留
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(
                self.lang_manager.get(
                    "error_msg", self.lang_manager.get("test_file_not_found_error")
                )
            )

            self.current_speed_test_status_key_and_args = ("not_tested", [])  # 重置状态
            self.speed_test_status_var.set(
                self.lang_manager.get(*self.current_speed_test_status_key_and_args)
            )
            self.speed_test_button.config(state=tk.NORMAL)
            self.speed_test_running = False
            messagebox.showerror(
                self.lang_manager.get("error_title"),
                f"测试文件不存在，请确保 {demo_dir} 目录下有 tv-report-1.mp4 和 tv-report-1.wav 文件",
            )  # 路径信息暂不翻译
            return

        # 记录文件大小和路径
        mp4_size = os.path.getsize(mp4_file)
        wav_size = os.path.getsize(wav_file)
        self.test_files = [mp4_file, wav_file]
        self.file_sizes = [mp4_size, wav_size]

        logging.info(
            self.lang_manager.get(
                "speed_test_event_start",
                os.path.basename(mp4_file),
                mp4_size / 1024 / 1024,
                os.path.basename(wav_file),
                wav_size / 1024 / 1024,
            )
        )

        # 启动第一次测试
        self._run_speed_test()

    def _run_speed_test(self):
        """运行单个文件的速度测试"""
        if self.test_file_index >= len(self.test_files):
            # 所有测试完成，计算并显示结果
            self._calculate_and_show_results()
            return

        current_file = self.test_files[self.test_file_index]
        file_name = os.path.basename(current_file)

        # 更新状态
        self.current_speed_test_status_key_and_args = (
            "test_progress",
            [self.test_file_index + 1],
        )
        self.speed_test_status_var.set(
            self.lang_manager.get(*self.current_speed_test_status_key_and_args)
        )
        # 使用StatusManager显示处理状态
        self.status_manager.set_processing(
            self.lang_manager.get("status_testing_file", file_name)
        )
        logging.info(
            self.lang_manager.get(
                "speed_test_event_testing_file", self.test_file_index + 1, current_file
            )
        )

        # 在新线程中运行测试，不阻塞UI
        threading.Thread(
            target=self._process_test_file, args=(current_file,), daemon=True
        ).start()

    def _process_test_file(self, file_path):
        """处理单个测试文件，记录上传时间和转写时间"""
        ip = self.ip_var.get()
        port = self.port_var.get()

        # 设置参数
        script_path = self._find_script_path()
        if not script_path:
            logging.error("系统错误: 未找到 simple_funasr_client.py 脚本")
            self.after(0, self._handle_test_error, "脚本未找到")
            return

        # 设置输出目录到 dev/output/speed_test 文件夹（遵循架构设计文档）
        results_dir = os.path.join(self.output_dir, "speed_test")
        os.makedirs(results_dir, exist_ok=True)

        args = [
            sys.executable,  # 使用当前 Python 解释器
            script_path,
            "--host",
            ip,
            "--port",
            str(port),
            "--audio_in",
            file_path,
            "--output_dir",
            results_dir,
        ]

        if self.use_itn_var.get() == 0:
            args.append("--no-itn")
        if self.use_ssl_var.get() == 0:
            args.append("--no-ssl")

        upload_start_time = None
        upload_end_time = None
        transcribe_start_time = None
        transcribe_end_time = None
        subprocess_timed_out = False  # 标记子进程是否因等待服务器超时而结束

        try:
            logging.debug(f"调试信息: 执行速度测试命令: {' '.join(args)}")
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )

            # 并发读取stderr，直接透出异常栈
            def _read_stderr_stream(stream):
                try:
                    for err_line in iter(stream.readline, ""):
                        if not err_line:
                            break
                        logging.error(f"{self.lang_manager.get('subprocess_error')}\n{err_line.strip()}")
                except Exception:
                    pass

            err_thread = threading.Thread(target=_read_stderr_stream, args=(process.stderr,), daemon=True)
            err_thread.start()

            # 实时读取输出，查找上传开始、结束和转写完成的标志
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break

                line = line.strip()
                logging.debug(f"速度测试输出: {line}")

                # 检测上传开始（匹配实际的日志输出格式）
                if (
                    ("发送初始化消息:" in line or "发送WebSocket:" in line)
                    and "mode" in line
                    and upload_start_time is None
                ):
                    upload_start_time = time.time()
                    logging.info(
                        self.lang_manager.get(
                            "speed_test_upload_started", self.test_file_index + 1
                        )
                    )

                # 检测上传进度，当进度达到100%时认为上传结束
                if "上传进度: 100%" in line and upload_end_time is None:
                    upload_end_time = time.time()
                    transcribe_start_time = time.time()  # 上传结束即开始转写
                    # 安全检查：确保upload_start_time不为None
                    if upload_start_time is not None:
                        logging.info(
                            self.lang_manager.get(
                                "speed_test_upload_completed",
                                self.test_file_index + 1,
                                upload_end_time - upload_start_time,
                            )
                        )
                    else:
                        logging.warning(
                            f"速度测试警告: 文件{self.test_file_index + 1}未检测到上传开始时间，无法计算上传耗时"
                        )

                # 兜底：如果收到 is_speaking=false 指令，也视作上传阶段结束
                if (
                    "发送WebSocket:" in line
                    and '"is_speaking": false' in line.replace(" ", "").lower()
                    and upload_end_time is None
                ):
                    upload_end_time = time.time()
                    transcribe_start_time = upload_end_time
                    if upload_start_time is not None:
                        logging.info(
                            self.lang_manager.get(
                                "speed_test_upload_completed",
                                self.test_file_index + 1,
                                upload_end_time - upload_start_time,
                            )
                        )

                # 检测转写完成（匹配实际的日志输出格式）
                # 优先级1: 收到 is_final=True 结束标志（最可靠的完成信号）
                if (
                    "离线识别完成" in line
                    or "实时识别完成" in line
                    or "离线模式收到非空文本" in line
                    or "收到结束标志或完整结果" in line
                ) and transcribe_end_time is None:
                    transcribe_end_time = time.time()
                    # 安全检查：确保transcribe_start_time不为None
                    if transcribe_start_time is not None:
                        logging.info(
                            self.lang_manager.get(
                                "speed_test_transcription_completed",
                                self.test_file_index + 1,
                                transcribe_end_time - transcribe_start_time,
                            )
                        )
                    else:
                        logging.warning(
                            f"速度测试警告: 文件{self.test_file_index + 1}未检测到转写开始时间，无法计算转写耗时"
                        )

                # 优先级2: 收到有效识别结果（服务器返回了文本但可能未设置 is_final）
                # 当服务器未设置 is_final=True 时，识别结果输出是转写完成的直接证据
                if (
                    "识别结果:" in line
                    and len(line) > len("识别结果:")  # 确保不是空结果
                    and transcribe_end_time is None
                ):
                    transcribe_end_time = time.time()
                    if transcribe_start_time is not None:
                        logging.info(
                            self.lang_manager.get(
                                "speed_test_transcription_completed",
                                self.test_file_index + 1,
                                transcribe_end_time - transcribe_start_time,
                            )
                        )
                        logging.info(
                            f"速度测试: 通过识别结果输出检测到转写完成"
                        )
                    else:
                        logging.warning(
                            f"速度测试警告: 文件{self.test_file_index + 1}未检测到转写开始时间，无法计算转写耗时"
                        )

                # 检测子进程等待服务器超时（服务器在指定时间内未返回结果）
                if "等待超时" in line:
                    subprocess_timed_out = True
                    logging.warning(
                        f"速度测试警告: 文件{self.test_file_index + 1}等待服务器响应超时 - {line}"
                    )

            # 确保进程结束（设置超时避免无限等待）
            try:
                process.wait(timeout=600)  # 最多等待10分钟
            except subprocess.TimeoutExpired:
                logging.warning("速度测试警告: 子进程执行超时，正在终止进程")
                self._terminate_process_safely(process, timeout=5, process_name="速度测试进程")
                self.after(0, self._handle_test_error, "速度测试超时")
                return

            # 检查是否成功获取了所有时间点
            if (
                upload_start_time
                and upload_end_time
                and transcribe_start_time
                and transcribe_end_time
            ):
                upload_time = upload_end_time - upload_start_time
                transcribe_time = transcribe_end_time - transcribe_start_time

                # 记录时间
                self.upload_times.append(upload_time)
                self.transcribe_times.append(transcribe_time)

                logging.info(
                    self.lang_manager.get(
                        "speed_test_file_completed",
                        self.test_file_index + 1,
                        upload_time,
                        transcribe_time,
                    )
                )

                # 准备下一个测试
                self.test_file_index += 1
                self.after(0, self._run_speed_test)
            else:
                # 某些时间点未能获取到
                missing = []
                if not upload_start_time:
                    missing.append("上传开始时间")
                if not upload_end_time:
                    missing.append("上传结束时间")
                if not transcribe_start_time:
                    missing.append("转写开始时间")
                if not transcribe_end_time:
                    missing.append("转写结束时间")

                # 根据不同情况提供更有针对性的错误信息
                if subprocess_timed_out and not transcribe_end_time:
                    error_msg = (
                        f"服务器在规定时间内未返回识别结果。"
                        f"请检查: 1) 服务器是否正常运行; "
                        f"2) 网络连接是否稳定; "
                        f"3) 测试文件格式是否被服务器支持"
                    )
                else:
                    error_msg = f"未能获取到完整时间点: {', '.join(missing)}"

                logging.error(
                    self.lang_manager.get(
                        "speed_test_error_missing_timestamps", ", ".join(missing)
                    )
                )
                # 若仅建立连接无上传，提供更明确提示
                if upload_start_time is None:
                    logging.warning("速度测试提示: 连接可能已建立，但未开始上传数据，请检查服务协议或网络限制。")
                self.after(0, self._handle_test_error, error_msg)

        except Exception as e:
            error_details = traceback.format_exc()
            logging.error(
                self.lang_manager.get(
                    "speed_test_error_general", f"{e}\n{error_details}"
                )
            )
            # 确保进程被终止
            if process and process.poll() is None:
                self._terminate_process_safely(process, timeout=5, process_name="速度测试进程(异常)")
            self.after(0, self._handle_test_error, str(e))

    def _handle_test_error(self, error_msg):
        """处理测试过程中的错误"""
        self.current_speed_test_status_key_and_args = ("test_failed_status", [])
        self.speed_test_status_var.set(
            self.lang_manager.get(*self.current_speed_test_status_key_and_args)
        )
        # 使用StatusManager显示错误状态
        self.status_manager.set_error(
            self.lang_manager.get("status_speed_test_failed_with_msg", error_msg)
        )
        self.speed_test_button.config(state=tk.NORMAL)
        self.speed_test_running = False
        messagebox.showerror(
            self.lang_manager.get("dialog_speed_test_error_title"),
            self.lang_manager.get("dialog_speed_test_error_msg", error_msg),
        )

    def _calculate_and_show_results(self):
        """计算并显示测试结果"""
        try:
            if len(self.upload_times) != 2 or len(self.transcribe_times) != 2:
                raise ValueError("测试数据不完整")

            # 计算上传速度 (MB/s)
            total_size_bytes = sum(self.file_sizes)
            total_size_mb = total_size_bytes / (1024 * 1024)
            total_upload_time = sum(self.upload_times)
            upload_speed = total_size_mb / total_upload_time

            # 计算转写速度 (倍速)
            # 两个文件播放时长各为180秒，总共360秒
            total_audio_duration = 360  # 两个文件各3分钟，共6分钟
            total_transcribe_time = sum(self.transcribe_times)
            transcribe_speed = total_audio_duration / total_transcribe_time

            # 更新UI显示
            self.upload_speed_var.set(f"{upload_speed:.2f} MB/s")
            self.transcribe_speed_var.set(f"{transcribe_speed:.2f}x")

            # 更新状态
            self.current_speed_test_status_key_and_args = ("test_completed", [])
            self.speed_test_status_var.set(
                self.lang_manager.get(*self.current_speed_test_status_key_and_args)
            )
            # 使用StatusManager显示成功状态
            self.status_manager.set_success(
                self.lang_manager.get("test_completed")
            )  # 使用通用的 test_completed
            self.speed_test_button.config(state=tk.NORMAL)
            self.speed_test_running = False

            logging.info(
                self.lang_manager.get(
                    "speed_test_results_log", upload_speed, transcribe_speed
                )
            )

            # 更新时长管理器的测速结果
            self.time_manager.set_speed_test_results(upload_speed, transcribe_speed)
            logging.debug(
                f"已更新转写时长管理器: 上传速度 {upload_speed:.2f} MB/s, 转写倍速 {transcribe_speed:.2f}x"
            )

            # 显示详细结果
            detail_msg = (
                f"{self.lang_manager.get('speed_test_summary_title')}\n\n"
                f"{self.lang_manager.get('total_file_size')}: {total_size_mb:.2f} MB\n"
                f"{self.lang_manager.get('total_upload_time')}: {total_upload_time:.2f} {self.lang_manager.get('seconds_unit')}\n"
                f"{self.lang_manager.get('average_upload_speed')}: {upload_speed:.2f} MB/s\n\n"
                f"{self.lang_manager.get('total_audio_duration')}: {total_audio_duration} {self.lang_manager.get('seconds_unit')}\n"
                f"{self.lang_manager.get('total_transcription_time')}: {total_transcribe_time:.2f} {self.lang_manager.get('seconds_unit')}\n"
                f"{self.lang_manager.get('transcription_speed_label')}: {transcribe_speed:.2f}x"
            )
            messagebox.showinfo(
                self.lang_manager.get("speed_test_result_title"), detail_msg
            )

        except Exception as e:
            error_details = traceback.format_exc()
            logging.error(
                self.lang_manager.get(
                    "speed_test_calculation_failed", f"{e}\n{error_details}"
                )
            )
            self.current_speed_test_status_key_and_args = (
                "result_calculation_failed_status",
                [],
            )
            self.speed_test_status_var.set(
                self.lang_manager.get(*self.current_speed_test_status_key_and_args)
            )
            # 使用StatusManager显示错误状态
            self.status_manager.set_error(
                self.lang_manager.get("status_speed_test_calc_failed", str(e))
            )
            self.speed_test_button.config(state=tk.NORMAL)
            self.speed_test_running = False
            messagebox.showerror(
                self.lang_manager.get("calculation_failed"),
                self.lang_manager.get("dialog_result_calc_failed_msg", str(e)),
            )


if __name__ == "__main__":
    # Ensure the script runs from its directory for relative paths to work correctly
    # os.chdir(os.path.dirname(os.path.abspath(__file__))) # Maybe not needed if resources are handled well
    app = FunASRGUIClient()
    app.mainloop()
