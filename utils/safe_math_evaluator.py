"""
安全的数学表达式求值器
用于替代不安全的 eval() 函数
"""
import ast
import operator
import logging
import math

logger = logging.getLogger(__name__)

class SafeMathEvaluator:
    """安全的数学表达式求值器"""
    
    # 允许的操作符
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.Mod: operator.mod,
    }
    
    # 允许的函数
    functions = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
    }
    
    # 允许的常量
    constants = {
        'pi': math.pi,
        'e': math.e,
    }
    
    @classmethod
    def eval_expr(cls, expression: str) -> float:
        """
        安全地计算数学表达式
        
        Args:
            expression: 数学表达式字符串
            
        Returns:
            计算结果
            
        Raises:
            ValueError: 当表达式无效或包含不允许的操作时
        """
        try:
            # 移除空白字符
            expression = expression.strip()
            
            # 基本长度检查
            if len(expression) > 100:
                raise ValueError("表达式过长")
            
            # 解析表达式
            node = ast.parse(expression, mode='eval')
            result = cls._eval_node(node.body)
            
            # 确保结果是数字
            if isinstance(result, (int, float)):
                if math.isnan(result) or math.isinf(result):
                    raise ValueError("计算结果无效（NaN或无限大）")
                return float(result)
            else:
                raise ValueError(f"表达式结果不是数字: {type(result)}")
                
        except SyntaxError as e:
            logger.warning(f"数学表达式语法错误: {expression}, 错误: {e}")
            raise ValueError(f"表达式语法错误: {str(e)}")
        except Exception as e:
            logger.warning(f"数学表达式求值失败: {expression}, 错误: {e}")
            raise ValueError(f"无效的数学表达式: {str(e)}")
    
    @classmethod
    def _eval_node(cls, node):
        """递归计算AST节点"""
        if isinstance(node, ast.Constant):  # Python 3.8+
            if isinstance(node.value, (int, float)):
                return node.value
            else:
                raise ValueError(f"不支持的常量类型: {type(node.value)}")
        elif isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            op = cls.operators.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的操作符: {type(node.op).__name__}")
            
            # 防止除零
            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("除零错误")
            
            # 防止过大的指数运算
            if isinstance(node.op, ast.Pow) and (abs(left) > 1000 or abs(right) > 100):
                raise ValueError("指数运算数值过大")
            
            result = op(left, right)
            
            # 检查结果是否合理
            if abs(result) > 1e15:
                raise ValueError("计算结果过大")
            
            return result
        elif isinstance(node, ast.UnaryOp):
            operand = cls._eval_node(node.operand)
            op = cls.operators.get(type(node.op))
            if op is None:
                raise ValueError(f"不支持的一元操作符: {type(node.op).__name__}")
            return op(operand)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("不支持的函数调用形式")
            
            func_name = node.func.id
            if func_name not in cls.functions:
                raise ValueError(f"不支持的函数: {func_name}")
            
            args = [cls._eval_node(arg) for arg in node.args]
            
            # 检查参数数量
            if len(args) > 10:
                raise ValueError("函数参数过多")
            
            return cls.functions[func_name](*args)
        elif isinstance(node, ast.Name):
            if node.id in cls.constants:
                return cls.constants[node.id]
            else:
                raise ValueError(f"不支持的变量: {node.id}")
        else:
            raise ValueError(f"不支持的表达式类型: {type(node).__name__}")

# 全局实例
safe_math = SafeMathEvaluator()

def safe_eval_math(expression: str) -> float:
    """安全地计算数学表达式的便捷函数"""
    return safe_math.eval_expr(expression)
