"""
自定义脚本加载器
负责动态加载custom_scripts目录中的Python脚本
"""
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class CustomScriptLoader:
    """自定义脚本加载器"""
    
    def __init__(self, scripts_dir: str = "custom_scripts"):
        self.scripts_dir = Path(scripts_dir)
        self.loaded_scripts: Dict[str, Any] = {}
        
    def load_scripts(self, bot_context: Dict[str, Any] | None = None) -> bool:
        """
        加载所有自定义脚本
        
        Args:
            bot_context: 机器人上下文，包含cache_manager、rate_converter等
            
        Returns:
            bool: 是否成功加载所有脚本
        """
        if not self.scripts_dir.exists():
            logger.warning(f"自定义脚本目录不存在: {self.scripts_dir}")
            return False
            
        if not self.scripts_dir.is_dir():
            logger.error(f"脚本路径不是目录: {self.scripts_dir}")
            return False
            
        # 获取所有Python脚本文件
        script_files = self._get_script_files()
        
        if not script_files:
            logger.info("没有找到自定义脚本文件")
            return True
            
        logger.info(f"发现 {len(script_files)} 个自定义脚本文件")
        
        success_count = 0
        
        # 按文件名排序加载
        for script_file in sorted(script_files):
            try:
                success = self._load_single_script(script_file, bot_context)
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"加载脚本 {script_file.name} 时发生未预期错误: {e}", exc_info=True)
                
        logger.info(f"自定义脚本加载完成: {success_count}/{len(script_files)} 成功")
        return success_count == len(script_files)
    
    def _get_script_files(self) -> List[Path]:
        """获取所有Python脚本文件"""
        script_files = []
        
        for file_path in self.scripts_dir.iterdir():
            if (file_path.is_file() and 
                file_path.suffix == '.py' and 
                not file_path.name.startswith('_') and
                file_path.name != '__init__.py'):
                script_files.append(file_path)
                
        return script_files
    
    def _load_single_script(self, script_file: Path, bot_context: Dict[str, Any] | None = None) -> bool:
        """
        加载单个脚本文件
        
        Args:
            script_file: 脚本文件路径
            bot_context: 机器人上下文
            
        Returns:
            bool: 是否加载成功
        """
        script_name = script_file.stem
        
        try:
            logger.info(f"正在加载自定义脚本: {script_name}")
            
            # 创建模块规范
            spec = importlib.util.spec_from_file_location(
                f"custom_scripts.{script_name}", 
                script_file
            )
            
            if spec is None or spec.loader is None:
                logger.error(f"无法创建脚本模块规范: {script_name}")
                return False
                
            # 创建模块
            module = importlib.util.module_from_spec(spec)
            
            # 将机器人上下文注入到模块中（如果提供了上下文）
            if bot_context:
                for key, value in bot_context.items():
                    setattr(module, key, value)
                    
            # 添加到sys.modules以便脚本可以相互导入
            sys.modules[f"custom_scripts.{script_name}"] = module
            
            # 执行模块
            spec.loader.exec_module(module)
            
            # 检查并调用 load 函数
            if hasattr(module, 'load') and callable(module.load):
                logger.info(f"执行脚本 {script_name} 的 load() 函数...")
                module.load(bot_context or {})
            else:
                logger.warning(f"脚本 {script_name} 没有找到可执行的 load() 函数。")

            # 尝试获取脚本信息
            script_info = self._get_script_info(module, script_name)
            
            # 存储已加载的脚本
            self.loaded_scripts[script_name] = {
                'module': module,
                'file_path': script_file,
                'info': script_info
            }
            
            logger.info(f"✅ 成功加载自定义脚本: {script_name}")
            if script_info.get('description'):
                logger.info(f"   描述: {script_info['description']}")
                
            return True
            
        except Exception as e:
            logger.error(f"❌ 加载自定义脚本失败: {script_name} - {e}", exc_info=True)
            return False
    
    def _get_script_info(self, module: Any, script_name: str) -> Dict[str, str]:
        """获取脚本信息"""
        default_info = {
            'name': script_name,
            'version': '未知',
            'description': '无描述',
            'author': '未知'
        }
        
        try:
            # 尝试调用get_script_info函数
            if hasattr(module, 'get_script_info') and callable(module.get_script_info):
                info = module.get_script_info()
                if isinstance(info, dict):
                    default_info.update(info)
        except Exception as e:
            logger.warning(f"获取脚本 {script_name} 信息时出错: {e}")
            
        return default_info
    
    def get_loaded_scripts(self) -> Dict[str, Dict[str, Any]]:
        """获取已加载的脚本列表"""
        return self.loaded_scripts.copy()
    
    def reload_script(self, script_name: str, bot_context: Dict[str, Any] | None = None) -> bool:
        """
        重新加载指定脚本
        
        Args:
            script_name: 脚本名称
            bot_context: 机器人上下文
            
        Returns:
            bool: 是否重新加载成功
        """
        if script_name not in self.loaded_scripts:
            logger.error(f"脚本 {script_name} 未加载，无法重新加载")
            return False
            
        script_file = self.loaded_scripts[script_name]['file_path']
        
        # 从sys.modules中移除旧模块
        module_name = f"custom_scripts.{script_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
            
        # 从已加载脚本中移除
        del self.loaded_scripts[script_name]
        
        # 重新加载
        return self._load_single_script(script_file, bot_context)

# 全局脚本加载器实例
script_loader = None

def init_script_loader(scripts_dir: str = "custom_scripts") -> CustomScriptLoader:
    """初始化脚本加载器"""
    global script_loader
    script_loader = CustomScriptLoader(scripts_dir)
    return script_loader

def get_script_loader() -> CustomScriptLoader | None:
    """获取脚本加载器实例"""
    return script_loader
