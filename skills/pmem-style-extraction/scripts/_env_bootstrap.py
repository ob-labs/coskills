#!/usr/bin/env python3
"""
环境自举（合并模式）：
优先级：pmem-key.env/系统环境变量 > skill/config/env.example > .env
"""

import os
from pathlib import Path
from typing import Dict, List

from dotenv import dotenv_values, load_dotenv


def _init_shared_config(skill_root: Path) -> Path:
    """
    初始化共享配置目录（skills/pmem-config/）：
    1. 检查共享配置目录是否存在
    2. 不存在 → 创建并从当前 skill 的 example 文件拷贝
    3. 已存在 → 直接返回（配置已由其他 skill 初始化）
    """
    shared_config_dir = skill_root.parent / "pmem-config"
    
    if not shared_config_dir.exists():
        # 首次使用，初始化共享配置
        shared_config_dir.mkdir(parents=True, exist_ok=True)
        
        # 拷贝 pmem-key.env.example → pmem-config/pmem-key.env
        key_example = skill_root / "config" / "pmem-key.env.example"
        shared_key = shared_config_dir / "pmem-key.env"
        if key_example.exists():
            shared_key.write_text(
                key_example.read_text(encoding="utf-8"),
                encoding="utf-8"
            )
        
    return shared_config_dir


def _resolve_env_example(skill_root: Path) -> Path:
    """返回当前 skill 的 env.example 路径。"""
    local_example = skill_root / "config" / "env.example"
    if local_example.exists():
        return local_example
    
    raise RuntimeError("未找到配置文件（请确认 skill/config/env.example 存在）")


def _resolve_pmem_key_file(skill_root: Path) -> Path:
    """返回共享配置目录中的 pmem-key.env 路径"""
    shared_config_dir = skill_root.parent / "pmem-config"
    return shared_config_dir / "pmem-key.env"


def _read_env_map(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    parsed = dotenv_values(path)
    output: Dict[str, str] = {}
    for key, value in parsed.items():
        if key is None:
            continue
        output[key] = "" if value is None else str(value)
    return output


def _read_key_order(path: Path) -> List[str]:
    if not path.exists():
        return []
    ordered: List[str] = []
    seen = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and key not in seen:
            ordered.append(key)
            seen.add(key)
    return ordered


def _write_merged_env(env_file: Path, merged: Dict[str, str], ordered_keys: List[str]) -> None:
    lines: List[str] = []
    emitted = set()
    for key in ordered_keys:
        if key in merged and key not in emitted:
            lines.append(f"{key}={merged[key]}")
            emitted.add(key)

    for key in sorted(merged.keys()):
        if key not in emitted:
            lines.append(f"{key}={merged[key]}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def bootstrap_env() -> Path:
    """确保 .env 可用并完成按优先级合并加载。"""
    skill_root = Path(__file__).resolve().parents[1]
    
    # 先初始化共享配置（如果不存在会创建）
    _init_shared_config(skill_root)
    
    env_file = skill_root / ".env"
    env_example = _resolve_env_example(skill_root)
    pmem_key_file = _resolve_pmem_key_file(skill_root)

    # 读取三层配置（低 -> 高）
    env_current = _read_env_map(env_file)            # 最低优先级
    env_template = _read_env_map(env_example)        # 中优先级
    env_keys = _read_env_map(pmem_key_file)          # 高优先级

    merged: Dict[str, str] = {}
    merged.update(env_current)
    merged.update(env_template)
    merged.update(env_keys)

    # 系统环境变量与 pmem-key 同级高优先级，最终覆盖
    candidate_keys = set(merged.keys())
    for key in candidate_keys:
        value = os.getenv(key)
        if value:
            merged[key] = value

    ordered_keys = []
    ordered_keys.extend(_read_key_order(env_example))
    ordered_keys.extend([k for k in _read_key_order(env_file) if k not in ordered_keys])
    ordered_keys.extend([k for k in _read_key_order(pmem_key_file) if k not in ordered_keys])

    _write_merged_env(env_file, merged, ordered_keys)

    # 加载最终 .env 到进程环境
    load_dotenv(dotenv_path=env_file, override=True)

    return env_file
