"""
OneNET Relay — HTTP 轮询 inventory_json + 前端上传(队列/重试/死信) + WS 推送
绝不连接 MQTT，避免干扰 ESP32 (device_01)
"""
import json
import time
import os
import uuid
import hmac
import hashlib
import base64
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import quote

from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ONENET_CONFIG = {
    "productId": os.getenv("ONENET_PRODUCT_ID", "OAgTJW6fph"),
    "deviceName": os.getenv("ONENET_DEVICE_NAME", "device_01"),
    "deviceSecret": os.getenv("ONENET_DEVICE_SECRET", "bFY1YWlrdmJ4eDB4c3o2c2U1MnpuSUNKUG03dVZuZno="),
    "accessKey": os.getenv("ONENET_ACCESS_KEY", "oR2pXSsfacONMQGjZ3+TtWN79S+npUepxSklYeHBK5s="),
    "baseUrl": "https://iot-api.heclouds.com",
}

DEAD_LETTER_DIR = Path(__file__).parent.parent / "dead_letter"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

FAKE_INVENTORY_PIPE = (
    "鸡蛋|6|74|肉蛋生鲜类;"
    "西红柿|3|18|蔬菜;"
    "鸡胸肉|2|133|肉蛋生鲜类;"
    "牛奶|1|42|饮料乳品类;"
    "西兰花|1|34|蔬菜;"
    "苹果|4|52|水果;"
    "胡萝卜|2|37|蔬菜;"
    "豆腐|1|76|蔬菜;"
    "青椒|3|22|蔬菜;"
    "猪肉|1|395|肉蛋生鲜类;"
    "香蕉|3|89|水果;"
    "酸奶|2|72|饮料乳品类"
)
FALLBACK_FAILURE_THRESHOLD = 3

EN_TO_CN = {
    'fruit': '水果', 'vegetable': '蔬菜', 'meat_egg': '肉蛋生鲜类',
    'beverage_dairy': '饮料乳品类', 'packaged': '包装食品类',
}


def parse_compact_inventory(value: str) -> list:
    """'apple|3|52|水果;banana|2|89|水果' -> list of food dicts"""
    if not value or not value.strip():
        return []
    items = []
    for segment in value.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        parts = segment.split("|")
        if len(parts) < 4:
            continue
        try:
            items.append({
                "name": parts[0].strip(),
                "qty": int(parts[1]),
                "calories": int(parts[2]) if parts[2].strip() else None,
                "cat": parts[3].strip(),
                "fromCloud": True,
            })
        except (ValueError, IndexError):
            pass
    return items


def _generate_api_token(pid: str, access_key: str) -> str:
    v, r, e = "2020-05-29", f"products/{pid}", int(time.time()) + 3600
    s = f"{e}\nsha1\n{r}\n{v}"
    kb = base64.b64decode(access_key)
    sign = base64.b64encode(hmac.new(kb, s.encode(), hashlib.sha1).digest()).decode()
    return f"version={v}&res={quote(r, safe='')}&et={e}&method=sha1&sign={quote(sign, safe='')}"


def _classify_error(exc: Exception, onenet_code: Optional[int]) -> str:
    """返回 "retryable" | "fatal" """
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError,
                         httpx.RemoteProtocolError, httpx.NetworkError)):
        return "retryable"
    if onenet_code is not None:
        if onenet_code == 10411:
            return "retryable"
        if onenet_code in (400, 401, 403, 404):
            return "fatal"
    if isinstance(exc, OSError):
        return "retryable"
    return "fatal"


def _foods_to_pipe(foods: list) -> tuple[str, list]:
    """dict列表 -> (pipe字符串, food_items列表)"""
    # Fix #3: qty=0 项不再静默丢弃，而是保留在 pipe 中以标记删除
    # 原有逻辑: if q <= 0: continue → 静默跳过，OneNET 端无法感知删除
    # 修复后: qty=0 的项也写入 pipe，下游可通过 qty=0 判断食材已清空
    food_items, segments = [], []
    for f in foods:
        q = int(float(f.get('quantity', f.get('qty', 1))))
        q = max(0, q)
        name = f.get('name', '') or f.get('enName', '')
        if not name:
            continue
        cat_en = f.get('category', f.get('cat', 'packaged'))
        cat_cn = EN_TO_CN.get(cat_en, cat_en)
        cal = int(f.get('calories', 0) or 0)
        segments.append(f"{name}|{q}|{cal}|{cat_cn}")
        if q > 0:
            food_items.append({'name': name, 'qty': q, 'unit': f.get('unit', '个'),
                               'cat': cat_cn, 'calories': cal, 'fromCloud': True})
    return ';'.join(segments), food_items


@dataclass
class UploadTask:
    upload_id: str
    foods: list
    pipe_value: str
    food_items: list
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = MAX_RETRIES
    next_retry_at: float = 0.0
    status: str = "pending"
    last_error: Optional[str] = None


class OneNetRelay:

    def __init__(self, config: Optional[dict] = None):
        cfg = {**ONENET_CONFIG, **(config or {})}
        self._pid = cfg["productId"]
        self._device = cfg["deviceName"]
        self._access_key = cfg["accessKey"]
        self._base_url = cfg.get("baseUrl", "https://iot-api.heclouds.com")
        self._callbacks: list = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_value: Optional[str] = None
        self._poll_task: Optional[asyncio.Task] = None

        self._http: Optional[httpx.AsyncClient] = None
        self._upload_queue: asyncio.Queue[UploadTask] = asyncio.Queue(maxsize=64)
        self._upload_worker: Optional[asyncio.Task] = None
        self._pending_upload_id: Optional[str] = None
        self._latest_upload: Optional[str] = None
        self._dead_letter_dir = DEAD_LETTER_DIR
        self._consecutive_failures: int = 0
        self._fallback_used: bool = False

    def on_data(self, callback):
        self._callbacks.append(callback)

    # ── 上传入口 (替代旧 upload_foods) ──────────────────────

    async def enqueue_upload(self, foods: list) -> str:
        """前端食材入队，立即返回 upload_id。由后台 Worker 执行 HTTP 发送"""
        upload_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        pipe_value, food_items = _foods_to_pipe(foods)

        task = UploadTask(
            upload_id=upload_id,
            foods=foods,
            pipe_value=pipe_value,
            food_items=food_items,
        )

        # 去重：覆盖队列中旧的 pending 任务
        if self._pending_upload_id:
            logger.info(f"[Upload {upload_id}] Superseding pending upload {self._pending_upload_id}")
        self._pending_upload_id = upload_id

        await self._upload_queue.put(task)
        logger.info(f"[Upload {upload_id}] Queued, foods={len(food_items)}, "
                     f"pipe='{pipe_value[:80]}'")
        return upload_id

    # ── WebSocket 推送当前数据给新客户端 ────────────────────

    async def push_current(self, websocket):
        value = self._latest_upload or self._last_value
        if value:
            items = parse_compact_inventory(value)
            if items:
                payload = json.dumps(
                    {"type": "food_update", "foodItems": items, "isSnapshot": True},
                    ensure_ascii=False)
                try:
                    await websocket.send_text(payload)
                    logger.info(f"[OneNet Relay] Pushed {len(items)} items to new client"
                                f"{' (latest upload)' if self._latest_upload else ''}")
                except Exception as e:
                    logger.warning(f"[OneNet Relay] Push failed: {e}")

    # ── 生命周期 ───────────────────────────────────────────

    async def connect(self):
        self._loop = asyncio.get_running_loop()
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._upload_worker = asyncio.create_task(self._run_upload_worker())
        logger.info("[OneNet Relay] HTTP client & upload worker started")

    async def disconnect(self):
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        if self._upload_worker:
            self._upload_worker.cancel()
            self._upload_worker = None
        if self._http:
            await self._http.aclose()
            self._http = None
        logger.info("[OneNet Relay] Disconnected")

    # ── 轮询回调 ───────────────────────────────────────────

    def _emit(self, food_items: list):
        logger.info(f"[OneNet Relay] Emitting {len(food_items)} items to {len(self._callbacks)} callbacks")
        for cb in self._callbacks:
            try:
                asyncio.ensure_future(cb(food_items))
            except Exception as e:
                logger.error(f"[OneNet Relay] Callback error: {e}")

    def _emit_fallback(self):
        """云端不可用时推送假数据"""
        # Fix #10: 云端恢复后自动复位 _fallback_used，支持再次离线时重新推送假数据
        # 原有逻辑: _fallback_used 设为 True 后再也不复位 → 二次离线时永不推送
        # 修复后: 云端恢复时在 _poll_loop 中复位 _fallback_used = False
        if self._fallback_used:
            return
        self._fallback_used = True
        items = parse_compact_inventory(FAKE_INVENTORY_PIPE)
        logger.warning(f"[OneNet Relay] Cloud unavailable, pushing {len(items)} fallback items")
        self._emit(items)

    async def _poll_fetch(self) -> Optional[str]:
        """通过 httpx 连接池轮询 OneNET 属性历史（复用连接，避免 WinError 10054）"""
        try:
            token = _generate_api_token(self._pid, self._access_key)
            now_ms = int(time.time() * 1000)
            resp = await self._http.get(
                "/thingmodel/query-device-property-history",
                params={
                    "product_id": self._pid,
                    "device_name": self._device,
                    "identifier": "inventory_json",
                    "start_time": now_ms - 300000,
                    "end_time": now_ms,
                    "limit": 1,
                },
                headers={"Authorization": token, "Cache-Control": "no-cache"},
            )
            data = resp.json()
            if data.get("code") == 0:
                items = data.get("data", {}).get("list", [])
                if items:
                    return items[0].get("value", "")
        except Exception as e:
            logger.warning(f"[OneNet Relay] HTTP poll error: {e}")
        return None

    async def _poll_loop(self):
        # 首次轮询
        got_data = False
        try:
            value = await self._poll_fetch()
            if value:
                self._last_value = value
                items = parse_compact_inventory(value)
                if items:
                    self._emit(items)
                    got_data = True
                    self._consecutive_failures = 0
                    logger.info(f"[OneNet Relay] Initial poll: {len(items)} items")
        except Exception as e:
            logger.warning(f"[OneNet Relay] Initial poll error: {e}")

        if not got_data:
            self._consecutive_failures += 1
            if self._consecutive_failures >= FALLBACK_FAILURE_THRESHOLD:
                self._emit_fallback()

        # Fix #13: 自适应轮询间隔 — 失败时延迟，成功后恢复 500ms
        poll_interval = 0.5
        while True:
            await asyncio.sleep(poll_interval)
            try:
                value = await self._poll_fetch()
                if value and value != self._last_value:
                    logger.info(f"[OneNet Relay] HTTP poll data: {value[:100]}...")
                    items = parse_compact_inventory(value)
                    if items:
                        self._last_value = value
                        self._consecutive_failures = 0
                        poll_interval = 0.5  # 恢复快速轮询
                        self._fallback_used = False  # Fix #10: 云端恢复，允许再次触发假数据回退
                        if self._latest_upload and value == self._latest_upload:
                            logger.info("[OneNet Relay] Poll confirmed latest upload, clearing upload cache")
                        self._latest_upload = None
                        self._emit(items)
                elif value and value == self._last_value:
                    self._consecutive_failures = 0
                    poll_interval = 0.5
                    self._fallback_used = False  # Fix #10
                else:
                    self._consecutive_failures += 1
                    poll_interval = min(poll_interval * 2, 30.0)  # Fix #13: 退避 max 30s
                    if self._consecutive_failures >= FALLBACK_FAILURE_THRESHOLD:
                        self._emit_fallback()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[OneNet Relay] Poll error: {e}")
                self._consecutive_failures += 1
                poll_interval = min(poll_interval * 2, 30.0)
                if self._consecutive_failures >= FALLBACK_FAILURE_THRESHOLD:
                    self._emit_fallback()

    # ── 上传 Worker ────────────────────────────────────────

    async def _run_upload_worker(self):
        while True:
            try:
                task = await self._upload_queue.get()
                if task.status == "done":
                    self._upload_queue.task_done()
                    continue

                if task.upload_id != self._pending_upload_id and task.status == "pending":
                    logger.info(f"[Upload {task.upload_id}] Superseded, skipping")
                    self._upload_queue.task_done()
                    continue

                task.status = "executing"
                await self._execute_upload(task)
                self._upload_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[OneNet Relay] Upload worker error: {e}")

    async def _execute_upload(self, task: UploadTask):
        attempt = task.retry_count + 1
        elapsed = int((time.time() - task.created_at) * 1000)
        logger.info(f"[Upload {task.upload_id}] Execute attempt {attempt}/{task.max_retries}, "
                     f"queued={elapsed}ms")

        onenet_code = None
        error_msg = None

        try:
            token = _generate_api_token(self._pid, self._access_key)
            resp = await self._http.post(
                "/thingmodel/set-device-property",
                json={
                    "product_id": self._pid,
                    "device_name": self._device,
                    "params": {"inventory_json": task.pipe_value},
                },
                headers={"Authorization": token},
            )
            result = resp.json()
            onenet_code = result.get("code")

            if onenet_code == 0:
                task.status = "done"
                total_ms = int((time.time() - task.created_at) * 1000)
                logger.info(f"[Upload {task.upload_id}] Done after {attempt} attempt(s), "
                             f"total={total_ms}ms")
                self._latest_upload = task.pipe_value
                if self._pending_upload_id == task.upload_id:
                    self._pending_upload_id = None
                await self._broadcast_food_update(task)
                await self._notify_upload_status(task, "done")
                await self._replay_dead_letters()
                return
            else:
                error_msg = f"code={onenet_code} {result.get('msg', '')}"

        except httpx.TimeoutException:
            error_msg = "timeout"
        except httpx.ConnectError as e:
            error_msg = f"connect: {e}"
        except httpx.RemoteProtocolError as e:
            error_msg = f"protocol: {e}"
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"

        task.last_error = error_msg
        category = _classify_error(
            exc=Exception(error_msg) if onenet_code is None else None,
            onenet_code=onenet_code,
        )

        if category == "retryable" and task.retry_count < task.max_retries - 1:
            task.retry_count += 1
            delay = RETRY_BASE_DELAY * (2 ** (task.retry_count - 1))
            task.next_retry_at = time.time() + delay
            task.status = "pending"
            logger.warning(f"[Upload {task.upload_id}] Retry {task.retry_count}/{task.max_retries} "
                           f"in {delay:.0f}s, error={error_msg}")
            await self._notify_upload_status(task, "retrying")
            asyncio.create_task(self._schedule_retry(task, delay))
        else:
            task.status = "dead"
            logger.error(f"[Upload {task.upload_id}] Dead after {task.retry_count + 1} attempt(s), "
                          f"reason={error_msg}")
            if self._pending_upload_id == task.upload_id:
                self._pending_upload_id = None
            self._write_dead_letter(task)
            await self._notify_upload_failed(task)
            # 即使失败也广播给其他客户端（本地数据仍然有效）
            await self._broadcast_food_update(task)

    async def _schedule_retry(self, task: UploadTask, delay: float):
        await asyncio.sleep(delay)
        await self._upload_queue.put(task)

    # ── HTTP POST 发送 (httpx) ──────────────────────────────
    # 已整合在 _execute_upload 中

    # ── 广播与通知 ──────────────────────────────────────────

    async def _broadcast_food_update(self, task: UploadTask):
        from api.ws_relay import broadcast
        try:
            await broadcast({
                "type": "food_update",
                "foodItems": task.food_items,
                "isSnapshot": True,
            })
        except Exception as e:
            logger.warning(f"[Upload {task.upload_id}] Broadcast error: {e}")

    async def _notify_upload_status(self, task: UploadTask, status: str):
        from api.ws_relay import send_upload_status
        extra = {}
        if status == "retrying":
            extra = {
                "attempt": task.retry_count + 1,
                "max_attempts": task.max_retries,
                "next_retry_in_ms": int((task.next_retry_at - time.time()) * 1000),
                "error": task.last_error,
            }
        await send_upload_status(task.upload_id, status, **extra)

    async def _notify_upload_failed(self, task: UploadTask):
        from api.ws_relay import send_upload_failed
        await send_upload_failed(
            task.upload_id,
            f"{task.retry_count + 1} retries exhausted: {task.last_error}",
        )

    # ── 死信队列 ────────────────────────────────────────────

    def _write_dead_letter(self, task: UploadTask):
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        path = self._dead_letter_dir / f"{task.upload_id}.json"
        data = {
            "upload_id": task.upload_id,
            "foods": task.foods,
            "pipe_value": task.pipe_value,
            "created_at": task.created_at,
            "retry_count": task.retry_count + 1,
            "last_error": task.last_error,
            "failed_at": time.time(),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[Upload {task.upload_id}] Dead letter written: {path}")

    async def _replay_dead_letters(self):
        if not self._dead_letter_dir.exists():
            return
        files = sorted(self._dead_letter_dir.glob("*.json"))
        if not files:
            return

        logger.info(f"[OneNet Relay] Replaying {len(files)} dead letter(s)")
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("pipe_value") == self._last_value:
                    logger.info(f"[OneNet Relay] Dead letter {path.name} matches current value, skip")
                    path.unlink()
                    continue

                new_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                logger.info(f"[Upload {new_id}] Replayed from dead letter {path.name}")
                pipe_value, food_items = _foods_to_pipe(data["foods"])
                task = UploadTask(
                    upload_id=new_id,
                    foods=data["foods"],
                    pipe_value=pipe_value,
                    food_items=food_items,
                    retry_count=0,
                )
                await self._upload_queue.put(task)
                path.unlink()
            except Exception as e:
                logger.warning(f"[OneNet Relay] Dead letter replay error ({path.name}): {e}")

    # ── upload_foods 兼容旧接口 (供 ws_relay 回调) ──────────

    async def upload_foods(self, foods: list):
        """旧接口兼容：入队并返回 upload_id。不再直接发 HTTP"""
        return await self.enqueue_upload(foods)
