#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Netlify CLI AI - 智慧部署助手
自動分析專案、生成配置、一鍵部署到 Netlify

使用方式：
    python netlify_ai.py [專案路徑]
    python netlify_ai.py              # 使用當前目錄
    python netlify_ai.py ./my-project # 指定專案路徑
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Any


# ============================================================================
# 顏色輸出工具
# ============================================================================

class Colors:
    """終端機顏色代碼"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """印出標題"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}\n")


def print_info(text: str):
    """印出資訊"""
    print(f"{Colors.CYAN}ℹ {text}{Colors.END}")


def print_success(text: str):
    """印出成功訊息"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text: str):
    """印出警告"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str):
    """印出錯誤"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_step(step: int, total: int, text: str):
    """印出步驟"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}[{step}/{total}] {text}{Colors.END}")


def ask_yes_no(question: str, default: bool = True) -> bool:
    """詢問是/否問題"""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"{Colors.YELLOW}? {question} {suffix}: {Colors.END}").strip().lower()
        if answer == '':
            return default
        if answer in ['y', 'yes', '是']:
            return True
        if answer in ['n', 'no', '否']:
            return False
        print("  請輸入 y 或 n")


def ask_choice(question: str, options: List[str], default: int = 0) -> int:
    """詢問選擇題"""
    print(f"\n{Colors.YELLOW}? {question}{Colors.END}")
    for i, opt in enumerate(options):
        prefix = "→" if i == default else " "
        print(f"  {prefix} [{i + 1}] {opt}")

    while True:
        answer = input(f"  請輸入選項 (1-{len(options)}) [預設: {default + 1}]: ").strip()
        if answer == '':
            return default
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(f"  請輸入 1 到 {len(options)} 之間的數字")


def ask_input(question: str, default: str = "") -> str:
    """詢問文字輸入"""
    suffix = f" [預設: {default}]" if default else ""
    answer = input(f"{Colors.YELLOW}? {question}{suffix}: {Colors.END}").strip()
    return answer if answer else default


# ============================================================================
# 專案分析器
# ============================================================================

class ProjectAnalyzer:
    """專案分析器 - 自動偵測專案類型和結構"""

    def __init__(self, project_path: str):
        self.path = Path(project_path).resolve()
        self.files: List[str] = []
        self.analysis: Dict[str, Any] = {}

    def scan_files(self) -> List[str]:
        """掃描專案檔案"""
        self.files = []
        ignore_dirs = {'.git', 'node_modules', '__pycache__', '.netlify', 'venv', '.venv'}

        for root, dirs, files in os.walk(self.path):
            # 過濾掉不需要的目錄
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), self.path)
                self.files.append(rel_path)

        return self.files

    def detect_project_type(self) -> Dict[str, Any]:
        """偵測專案類型"""
        self.scan_files()

        analysis = {
            'type': 'static',  # static, python-functions, node-functions, full-stack
            'has_html': False,
            'has_python': False,
            'has_node': False,
            'has_netlify_config': False,
            'has_env_file': False,
            'has_env_example': False,
            'has_gitignore': False,
            'has_requirements': False,
            'has_package_json': False,
            'python_files': [],
            'env_vars_needed': [],
            'publish_dir': '.',
            'functions_dir': None,
            'build_command': None,
        }

        for file in self.files:
            file_lower = file.lower()

            # 檢查 HTML
            if file_lower.endswith('.html'):
                analysis['has_html'] = True

            # 檢查 Python
            if file_lower.endswith('.py'):
                analysis['has_python'] = True
                analysis['python_files'].append(file)

            # 檢查 Node.js
            if file_lower == 'package.json':
                analysis['has_node'] = True
                analysis['has_package_json'] = True

            # 檢查現有配置
            if file_lower == 'netlify.toml':
                analysis['has_netlify_config'] = True

            if file_lower == '.env':
                analysis['has_env_file'] = True

            if file_lower == '.env.example':
                analysis['has_env_example'] = True

            if file_lower == '.gitignore':
                analysis['has_gitignore'] = True

            if file_lower == 'requirements.txt':
                analysis['has_requirements'] = True

        # 判斷專案類型
        if analysis['has_python']:
            # 檢查是否有 functions 目錄結構
            for py_file in analysis['python_files']:
                if 'functions' in py_file.lower() or 'netlify' in py_file.lower():
                    analysis['type'] = 'python-functions'
                    # 找到 functions 目錄
                    parts = Path(py_file).parts
                    for i, part in enumerate(parts):
                        if 'functions' in part.lower():
                            analysis['functions_dir'] = str(Path(*parts[:i+1]))
                            break
                    break

            if analysis['type'] == 'static' and analysis['has_python']:
                # 有 Python 但不在 functions 目錄，可能需要設定
                analysis['type'] = 'python-functions'

        if analysis['has_node'] and analysis['has_package_json']:
            analysis['type'] = 'node-project'
            analysis['build_command'] = 'npm run build'

        # 檢測需要的環境變數
        analysis['env_vars_needed'] = self._detect_env_vars()

        self.analysis = analysis
        return analysis

    def _detect_env_vars(self) -> List[str]:
        """偵測可能需要的環境變數"""
        env_vars = set()
        patterns = [
            ('OPENAI_API_KEY', ['openai', 'gpt', 'chatgpt']),
            ('GOOGLE_API_KEY', ['google', 'gemini', 'generativeai']),
            ('ANTHROPIC_API_KEY', ['anthropic', 'claude']),
            ('DATABASE_URL', ['database', 'postgres', 'mysql', 'mongodb']),
            ('SECRET_KEY', ['secret', 'jwt', 'session']),
            ('API_KEY', ['api_key', 'apikey']),
        ]

        for file in self.files:
            if file.endswith(('.py', '.js', '.ts', '.jsx', '.tsx')):
                try:
                    file_path = self.path / file
                    content = file_path.read_text(encoding='utf-8', errors='ignore').lower()

                    for env_var, keywords in patterns:
                        if any(kw in content for kw in keywords):
                            env_vars.add(env_var)
                except Exception:
                    pass

        return list(env_vars)

    def print_analysis(self):
        """印出分析結果"""
        a = self.analysis

        print_header("專案分析結果")

        print(f"  專案路徑: {self.path}")
        print(f"  檔案數量: {len(self.files)}")
        print()

        type_names = {
            'static': '靜態網站 (HTML/CSS/JS)',
            'python-functions': 'Python Serverless Functions',
            'node-project': 'Node.js 專案',
            'node-functions': 'Node.js Serverless Functions',
        }
        print(f"  專案類型: {type_names.get(a['type'], a['type'])}")
        print()

        print("  偵測到的檔案:")
        print(f"    {'✓' if a['has_html'] else '✗'} HTML 檔案")
        print(f"    {'✓' if a['has_python'] else '✗'} Python 檔案")
        print(f"    {'✓' if a['has_node'] else '✗'} Node.js (package.json)")
        print()

        print("  現有配置:")
        print(f"    {'✓' if a['has_netlify_config'] else '✗'} netlify.toml")
        print(f"    {'✓' if a['has_gitignore'] else '✗'} .gitignore")
        print(f"    {'✓' if a['has_env_example'] else '✗'} .env.example")
        print(f"    {'✓' if a['has_requirements'] else '✗'} requirements.txt")
        print()

        if a['env_vars_needed']:
            print("  可能需要的環境變數:")
            for var in a['env_vars_needed']:
                print(f"    • {var}")


# ============================================================================
# 配置生成器
# ============================================================================

class ConfigGenerator:
    """配置檔生成器"""

    def __init__(self, project_path: str, analysis: Dict[str, Any]):
        self.path = Path(project_path).resolve()
        self.analysis = analysis

    def generate_netlify_toml(self,
                               publish_dir: str = ".",
                               functions_dir: Optional[str] = None,
                               build_command: Optional[str] = None,
                               python_version: str = "3.10") -> str:
        """生成 netlify.toml 內容"""

        lines = ['[build]']

        if functions_dir:
            lines.append(f'  functions = "{functions_dir}"')

        lines.append(f'  publish = "{publish_dir}"')

        if build_command:
            lines.append(f'  command = "{build_command}"')

        # Python 設定
        if self.analysis['has_python'] and functions_dir:
            lines.append('')
            lines.append('[functions]')
            lines.append(f'  python_version = "{python_version}"')

        # API 重定向
        if functions_dir:
            lines.append('')
            lines.append('[[redirects]]')
            lines.append('  from = "/api/*"')
            lines.append('  to = "/.netlify/functions/:splat"')
            lines.append('  status = 200')

        return '\n'.join(lines) + '\n'

    def generate_gitignore(self) -> str:
        """生成 .gitignore 內容"""
        return """# 環境變數（含敏感資訊）
.env
.env.local
.env.production

# Netlify 本地快取
.netlify/

# Python
__pycache__/
*.py[cod]
*$py.class
venv/
.venv/
*.egg-info/

# Node.js
node_modules/

# 系統檔案
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo
"""

    def generate_env_example(self, env_vars: List[str]) -> str:
        """生成 .env.example 內容"""
        lines = ['# 環境變數範例', '# 複製此檔案為 .env 並填入真實的值', '']

        descriptions = {
            'OPENAI_API_KEY': '# OpenAI API Key - https://platform.openai.com/api-keys',
            'GOOGLE_API_KEY': '# Google API Key (Gemini) - https://aistudio.google.com/app/apikey',
            'ANTHROPIC_API_KEY': '# Anthropic API Key - https://console.anthropic.com/',
            'DATABASE_URL': '# 資料庫連線字串',
            'SECRET_KEY': '# 應用程式密鑰',
            'API_KEY': '# API 金鑰',
        }

        for var in env_vars:
            if var in descriptions:
                lines.append(descriptions[var])
            lines.append(f'{var}=your_{var.lower()}_here')
            lines.append('')

        lines.append('# 注意：永遠不要將 .env 檔案上傳到 Git！')

        return '\n'.join(lines)

    def generate_requirements(self) -> str:
        """生成 requirements.txt 內容"""
        packages = []

        # 根據偵測到的環境變數推斷需要的套件
        env_vars = self.analysis.get('env_vars_needed', [])

        if 'OPENAI_API_KEY' in env_vars:
            packages.append('openai')

        if 'GOOGLE_API_KEY' in env_vars:
            packages.append('google-generativeai')

        if 'ANTHROPIC_API_KEY' in env_vars:
            packages.append('anthropic')

        if not packages:
            packages.append('# 在此加入你需要的 Python 套件')

        return '\n'.join(packages) + '\n'

    def write_file(self, filename: str, content: str, force: bool = False) -> bool:
        """寫入檔案"""
        file_path = self.path / filename

        if file_path.exists() and not force:
            if not ask_yes_no(f"  {filename} 已存在，要覆蓋嗎?", default=False):
                print_warning(f"跳過 {filename}")
                return False

        file_path.write_text(content, encoding='utf-8')
        print_success(f"已生成 {filename}")
        return True


# ============================================================================
# 部署器
# ============================================================================

class Deployer:
    """Netlify 部署器"""

    def __init__(self, project_path: str):
        self.path = Path(project_path).resolve()

    def check_netlify_cli(self) -> bool:
        """檢查 Netlify CLI 是否安裝"""
        try:
            result = subprocess.run(
                ['netlify', '--version'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def check_logged_in(self) -> bool:
        """檢查是否已登入 Netlify"""
        try:
            result = subprocess.run(
                ['netlify', 'status'],
                capture_output=True,
                text=True,
                cwd=str(self.path)
            )
            return 'Logged in' in result.stdout or 'logged in' in result.stdout.lower()
        except Exception:
            return False

    def login(self) -> bool:
        """執行 Netlify 登入"""
        print_info("正在開啟瀏覽器進行登入...")
        try:
            result = subprocess.run(
                ['netlify', 'login'],
                cwd=str(self.path)
            )
            return result.returncode == 0
        except Exception as e:
            print_error(f"登入失敗: {e}")
            return False

    def init_site(self) -> bool:
        """初始化 Netlify 網站"""
        print_info("正在初始化 Netlify 網站...")
        try:
            result = subprocess.run(
                ['netlify', 'init'],
                cwd=str(self.path)
            )
            return result.returncode == 0
        except Exception as e:
            print_error(f"初始化失敗: {e}")
            return False

    def set_env_var(self, key: str, value: str) -> bool:
        """設定環境變數"""
        try:
            result = subprocess.run(
                ['netlify', 'env:set', key, value],
                capture_output=True,
                text=True,
                cwd=str(self.path)
            )
            return result.returncode == 0
        except Exception:
            return False

    def deploy_preview(self) -> Optional[str]:
        """部署預覽版本"""
        print_info("正在部署預覽版本...")
        try:
            result = subprocess.run(
                ['netlify', 'deploy'],
                capture_output=True,
                text=True,
                cwd=str(self.path)
            )

            if result.returncode == 0:
                # 從輸出中找到 URL
                for line in result.stdout.split('\n'):
                    if 'Website Draft URL' in line or 'Website draft URL' in line:
                        url = line.split()[-1]
                        return url
            else:
                print_error(f"部署失敗:\n{result.stderr}")

            return None
        except Exception as e:
            print_error(f"部署失敗: {e}")
            return None

    def deploy_production(self) -> Optional[str]:
        """正式部署"""
        print_info("正在進行正式部署...")
        try:
            result = subprocess.run(
                ['netlify', 'deploy', '--prod'],
                capture_output=True,
                text=True,
                cwd=str(self.path)
            )

            if result.returncode == 0:
                # 從輸出中找到 URL
                for line in result.stdout.split('\n'):
                    if 'Website URL' in line:
                        url = line.split()[-1]
                        return url
            else:
                print_error(f"部署失敗:\n{result.stderr}")

            return None
        except Exception as e:
            print_error(f"部署失敗: {e}")
            return None


# ============================================================================
# 主程式
# ============================================================================

def show_main_menu() -> str:
    """顯示主選單並取得專案路徑"""
    print(f"\n{Colors.CYAN}請選擇操作方式：{Colors.END}")
    print()
    print(f"  {Colors.BOLD}[1]{Colors.END} 指定專案路徑    - 輸入要部署的專案資料夾路徑")
    print(f"  {Colors.BOLD}[2]{Colors.END} 使用當前目錄    - 部署目前所在的資料夾")
    print(f"  {Colors.BOLD}[3]{Colors.END} 瀏覽選擇資料夾  - 輸入路徑後確認")
    print()
    print(f"  {Colors.BOLD}[0]{Colors.END} 離開程式")
    print()

    while True:
        choice = input(f"{Colors.YELLOW}? 請輸入選項 (0-3): {Colors.END}").strip()

        if choice == '0':
            print_info("感謝使用，再見！")
            sys.exit(0)

        elif choice == '1':
            # 指定專案路徑
            project_path = input(f"{Colors.YELLOW}? 請輸入專案路徑: {Colors.END}").strip()
            if not project_path:
                print_warning("路徑不能為空")
                continue
            return project_path

        elif choice == '2':
            # 使用當前目錄
            return "."

        elif choice == '3':
            # 瀏覽選擇資料夾
            default_path = os.getcwd()
            print(f"\n  當前目錄: {default_path}")
            project_path = input(f"{Colors.YELLOW}? 請輸入專案路徑 [按 Enter 使用當前目錄]: {Colors.END}").strip()
            if not project_path:
                project_path = default_path
            return project_path

        else:
            print_warning("請輸入 0、1、2 或 3")


def main():
    """主程式入口"""
    print_header("Netlify CLI AI - 智慧部署助手")
    print(f"  {Colors.CYAN}曾慶良(阿亮老師)建置{Colors.END}")

    # 如果有命令列參數，直接使用
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
    else:
        # 顯示選單讓使用者選擇
        project_path = show_main_menu()

    # 確認路徑存在
    project_path = Path(project_path).resolve()
    if not project_path.exists():
        print_error(f"路徑不存在: {project_path}")
        sys.exit(1)

    if not project_path.is_dir():
        print_error(f"這不是一個資料夾: {project_path}")
        sys.exit(1)

    print_info(f"專案路徑: {project_path}")

    total_steps = 5

    # ========== 步驟 1: 分析專案 ==========
    print_step(1, total_steps, "分析專案結構")

    analyzer = ProjectAnalyzer(str(project_path))
    analysis = analyzer.detect_project_type()
    analyzer.print_analysis()

    if not ask_yes_no("分析結果正確嗎？要繼續嗎?"):
        print_info("已取消")
        sys.exit(0)

    # ========== 步驟 2: 確認配置 ==========
    print_step(2, total_steps, "確認部署配置")

    # 確認發布目錄
    publish_dir = ask_input("發布目錄 (靜態檔案所在位置)", default=".")

    # 確認 Functions 目錄
    functions_dir = None
    if analysis['has_python']:
        if analysis['functions_dir']:
            functions_dir = ask_input("Functions 目錄", default=analysis['functions_dir'])
        else:
            if ask_yes_no("要設定 Python Serverless Functions 嗎?"):
                functions_dir = ask_input("Functions 目錄", default="netlify/functions")

    # 確認建置指令
    build_command = None
    if analysis['has_node']:
        build_command = ask_input("建置指令 (如不需要請留空)", default="npm run build")
        if not build_command:
            build_command = None

    # ========== 步驟 3: 生成配置檔 ==========
    print_step(3, total_steps, "生成配置檔案")

    generator = ConfigGenerator(str(project_path), analysis)

    # 生成 netlify.toml
    if not analysis['has_netlify_config'] or ask_yes_no("要重新生成 netlify.toml 嗎?", default=False):
        content = generator.generate_netlify_toml(
            publish_dir=publish_dir,
            functions_dir=functions_dir,
            build_command=build_command
        )
        print("\n  預覽 netlify.toml:")
        print("  " + "-" * 40)
        for line in content.split('\n'):
            print(f"  {line}")
        print("  " + "-" * 40)

        if ask_yes_no("確定要寫入嗎?"):
            generator.write_file('netlify.toml', content, force=True)

    # 生成 .gitignore
    if not analysis['has_gitignore']:
        if ask_yes_no("要生成 .gitignore 嗎?"):
            content = generator.generate_gitignore()
            generator.write_file('.gitignore', content)

    # 生成 .env.example
    if not analysis['has_env_example'] and analysis['env_vars_needed']:
        if ask_yes_no("要生成 .env.example 嗎?"):
            content = generator.generate_env_example(analysis['env_vars_needed'])
            generator.write_file('.env.example', content)

    # 生成 requirements.txt (如果有 Python Functions)
    if functions_dir and not analysis['has_requirements']:
        if ask_yes_no("要生成 requirements.txt 嗎?"):
            content = generator.generate_requirements()
            req_path = Path(functions_dir) / 'requirements.txt'

            # 確保目錄存在
            (project_path / functions_dir).mkdir(parents=True, exist_ok=True)

            generator.write_file(str(req_path), content)

    # ========== 步驟 4: 準備部署 ==========
    print_step(4, total_steps, "準備部署")

    deployer = Deployer(str(project_path))

    # 檢查 Netlify CLI
    if not deployer.check_netlify_cli():
        print_error("未偵測到 Netlify CLI")
        print_info("請先安裝: npm install -g netlify-cli")
        print_info("配置檔已生成完畢，你可以手動執行部署")
        sys.exit(0)

    print_success("已偵測到 Netlify CLI")

    # 檢查登入狀態
    if not deployer.check_logged_in():
        print_warning("尚未登入 Netlify")
        if ask_yes_no("要現在登入嗎?"):
            if not deployer.login():
                print_error("登入失敗")
                sys.exit(1)
    else:
        print_success("已登入 Netlify")

    # ========== 步驟 5: 執行部署 ==========
    print_step(5, total_steps, "執行部署")

    if not ask_yes_no("準備好部署了嗎?"):
        print_info("已取消部署")
        print_info("你可以稍後執行: netlify deploy")
        sys.exit(0)

    # 初始化網站 (如果需要)
    if ask_yes_no("需要初始化新的 Netlify 網站嗎?", default=True):
        deployer.init_site()

    # 設定環境變數
    if analysis['env_vars_needed']:
        print("\n  需要設定以下環境變數:")
        for var in analysis['env_vars_needed']:
            print(f"    • {var}")

        if ask_yes_no("\n要現在設定環境變數嗎?"):
            for var in analysis['env_vars_needed']:
                value = ask_input(f"  {var}")
                if value:
                    if deployer.set_env_var(var, value):
                        print_success(f"已設定 {var}")
                    else:
                        print_warning(f"無法設定 {var}，請稍後手動設定")

    # 部署預覽
    preview_url = deployer.deploy_preview()
    if preview_url:
        print_success(f"預覽版本已部署: {preview_url}")

        if ask_yes_no("測試沒問題後，要進行正式部署嗎?"):
            prod_url = deployer.deploy_production()
            if prod_url:
                print_success(f"正式部署完成: {prod_url}")
            else:
                print_error("正式部署失敗")
    else:
        print_error("預覽部署失敗")

    # 完成
    print_header("部署完成！")
    print_info("感謝使用 Netlify CLI AI 智慧部署助手")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消操作")
        sys.exit(0)
