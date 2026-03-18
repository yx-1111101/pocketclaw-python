"""
MCP (Model Context Protocol) Service management API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging

router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)


class MCPService(BaseModel):
    """MCP 服务模型"""
    id: str
    name: str
    command: str
    args: Optional[str] = ""
    env: Optional[Dict[str, str]] = {}
    enabled: bool = False
    icon: str = "file"
    color: str = "#667eea"


class MCPServiceCreate(BaseModel):
    """创建 MCP 服务请求"""
    name: str
    command: str
    args: Optional[str] = ""
    env: Optional[Dict[str, str]] = {}
    icon: Optional[str] = "file"
    color: Optional[str] = "#667eea"


class MCPServiceUpdate(BaseModel):
    """更新 MCP 服务请求"""
    name: Optional[str] = None
    command: Optional[str] = None
    args: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None
    icon: Optional[str] = None
    color: Optional[str] = None


# 内存存储（生产环境应使用数据库）
_mcp_services: Dict[str, List[MCPService]] = {}


def _get_device_services(device_id: str) -> List[MCPService]:
    """获取设备的服务列表"""
    if device_id not in _mcp_services:
        # 初始化默认服务
        _mcp_services[device_id] = [
            MCPService(
                id="1",
                name="文件系统",
                command="npx -y @modelcontextprotocol/server-filesystem",
                enabled=True,
                icon="file",
                color="#34C759"
            ),
            MCPService(
                id="2",
                name="记忆存储",
                command="uvx mcp-memory",
                enabled=True,
                icon="brain",
                color="#5856D6"
            ),
            MCPService(
                id="3",
                name="网页抓取",
                command="uvx mcp-fetch",
                enabled=False,
                icon="globe",
                color="#007AFF"
            ),
        ]
    return _mcp_services[device_id]


@router.get("/services")
async def get_services(device_id: str = "default"):
    """获取 MCP 服务列表"""
    services = _get_device_services(device_id)
    
    return {
        "success": True,
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "command": s.command,
                "args": s.args,
                "enabled": s.enabled,
                "icon": s.icon,
                "color": s.color,
            }
            for s in services
        ]
    }


@router.get("/services/{service_id}")
async def get_service(device_id: str, service_id: str):
    """获取单个服务详情"""
    services = _get_device_services(device_id)
    
    service = next((s for s in services if s.id == service_id), None)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return {
        "success": True,
        "service": {
            "id": service.id,
            "name": service.name,
            "command": service.command,
            "args": service.args,
            "env": service.env,
            "enabled": service.enabled,
            "icon": service.icon,
            "color": service.color,
        }
    }


@router.post("/services")
async def create_service(device_id: str = "default", service: MCPServiceCreate = None):
    """创建 MCP 服务"""
    if service is None:
        raise HTTPException(status_code=400, detail="Request body required")
    
    services = _get_device_services(device_id)
    
    # 生成 ID
    new_id = str(uuid.uuid4())[:8]
    
    new_service = MCPService(
        id=new_id,
        name=service.name,
        command=service.command,
        args=service.args or "",
        env=service.env or {},
        enabled=False,
        icon=service.icon or "file",
        color=service.color or "#667eea"
    )
    
    services.append(new_service)
    
    return {
        "success": True,
        "service": {
            "id": new_service.id,
            "name": new_service.name,
            "command": new_service.command,
            "enabled": new_service.enabled,
        }
    }


@router.patch("/services/{service_id}")
async def update_service(device_id: str, service_id: str, update: MCPServiceUpdate):
    """更新 MCP 服务"""
    services = _get_device_services(device_id)
    
    service = next((s for s in services if s.id == service_id), None)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # 更新字段
    if update.name is not None:
        service.name = update.name
    if update.command is not None:
        service.command = update.command
    if update.args is not None:
        service.args = update.args
    if update.env is not None:
        service.env = update.env
    if update.enabled is not None:
        service.enabled = update.enabled
    if update.icon is not None:
        service.icon = update.icon
    if update.color is not None:
        service.color = update.color
    
    return {
        "success": True,
        "service": {
            "id": service.id,
            "name": service.name,
            "command": service.command,
            "enabled": service.enabled,
        }
    }


@router.delete("/services/{service_id}")
async def delete_service(device_id: str, service_id: str):
    """删除 MCP 服务"""
    services = _get_device_services(device_id)
    
    original_count = len(services)
    services = [s for s in services if s.id != service_id]
    
    if len(services) == original_count:
        raise HTTPException(status_code=404, detail="Service not found")
    
    _mcp_services[device_id] = services
    
    return {"success": True}


@router.post("/services/{service_id}/enable")
async def enable_service(device_id: str, service_id: str):
    """启用 MCP 服务"""
    services = _get_device_services(device_id)
    
    service = next((s for s in services if s.id == service_id), None)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # TODO: 实际调用设备 Gateway 启动服务
    service.enabled = True
    
    return {
        "success": True,
        "enabled": True
    }


@router.post("/services/{service_id}/disable")
async def disable_service(device_id: str, service_id: str):
    """禁用 MCP 服务"""
    services = _get_device_services(device_id)
    
    service = next((s for s in services if s.id == service_id), None)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # TODO: 实际调用设备 Gateway 停止服务
    service.enabled = False
    
    return {
        "success": True,
        "enabled": False
    }
