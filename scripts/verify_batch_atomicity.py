"""本地接口验证：作业记录批量上报的原子性、错误定位与幂等重试。

直接驱动一个真实的本地 uvicorn 进程（HTTP 调用），覆盖：
  1. 混合有效数据整批成功；
  2. 中间一条关联对象不存在 -> 整批 400 拒绝且零写入，错误指出原始 index 与原因；
  3. 中间一条在保存阶段异常 -> 同事务整体回滚，先前 flush 的记录不落库；
  4. 完全相同的载荷重试幂等；并在“重启服务进程”后再次提交仍不重复落库；
  5. 单条录入接口行为保持不变。

用法：.venv/bin/python scripts/verify_batch_atomicity.py
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
API = "/api/v1"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(db_path: str, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return proc
        except httpx.TransportError:
            pass
        time.sleep(0.25)
    proc.kill()
    out = proc.stdout.read() if proc.stdout else ""
    raise RuntimeError(f"服务未在限定时间内启动\n{out}")


def stop_server(proc: subprocess.Popen):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def op_payload(serial: str, *, duration_ms=None, scene_id=1, model_id=1, skill_id=1):
    return {
        "robot_model_id": model_id,
        "scene_id": scene_id,
        "skill_id": skill_id,
        "robot_serial": serial,
        "motion_trajectory": {"path": [1, 2, 3], "serial": serial},
        "perception_records": {"objects": 2},
        "grasp_result": {"ok": True},
        "timestamp_start": f"2026-09-24T10:00:{serial[-2:] if serial[-2:].isdigit() else '00'}",
        "timestamp_end": "2026-09-24T10:00:05",
        "duration_ms": duration_ms if duration_ms is not None else 5000,
    }


PASS, FAIL = "PASS", "FAIL"
results = []


def check(name: str, cond: bool, detail=""):
    results.append((name, cond, detail))
    print(f"[{PASS if cond else FAIL}] {name}" + (f"\n      -> {detail}" if detail and not cond else ""))


def main():
    tmpdir = tempfile.mkdtemp(prefix="batch_verify_")
    db_path = os.path.join(tmpdir, "verify.db")
    port = free_port()
    proc = start_server(db_path, port)
    base = f"http://127.0.0.1:{port}{API}"

    try:
        with httpx.Client(timeout=10) as c:
            # 基础资源
            model_id = c.post(f"{base}/robot-models", json={
                "name": "RM-VERIFY", "manufacturer": "RealMotion"}).json()["id"]
            scene_id = c.post(f"{base}/scenes", json={
                "name": "验证产线", "category": "生产制造"}).json()["id"]
            skill_id = c.post(f"{base}/skills", json={
                "name": "验证抓取", "category": "抓取"}).json()["id"]

            def op(serial, **overrides):
                params = {"model_id": model_id, "scene_id": scene_id, "skill_id": skill_id}
                params.update(overrides)
                return op_payload(serial, **params)

            # ---- 场景 1：混合有效数据整批成功 ----
            batch1 = [op("SN-01"), op("SN-02"), op("SN-03")]
            r = c.post(f"{base}/operations/batch", json=batch1)
            body = r.json()
            check("1. 有效批次返回 200", r.status_code == 200, f"status={r.status_code} body={body}")
            check("1. success_count=3 / failure_count=0",
                  body.get("success_count") == 3 and body.get("failure_count") == 0, str(body))
            check("1. 结果序号与原始输入位置一致(0,1,2)",
                  [it["index"] for it in body.get("results", [])] == [0, 1, 2], str(body))
            ids_first = [it["data"]["id"] for it in body["results"]]
            check("1. 返回记录按输入顺序且序列号对应",
                  [it["data"]["robot_serial"] for it in body["results"]] == ["SN-01", "SN-02", "SN-03"],
                  str(ids_first))
            check("1. 首次提交 replayed=False", body.get("replayed") is False, str(body.get("replayed")))

            count_after_1 = c.get(f"{base}/operations", params={"page_size": 200}).json()["total"]
            check("1. 库中恰好新增 3 条", count_after_1 == 3, f"total={count_after_1}")

            # ---- 场景 2：中间一条(index=1)关联场景不存在 -> 整批拒绝 ----
            batch_bad_fk = [op("SN-10"), op("SN-11", scene_id=999999), op("SN-12")]
            r = c.post(f"{base}/operations/batch", json=batch_bad_fk)
            check("2. 关联缺失批次返回 400", r.status_code == 400, f"status={r.status_code}")
            d = r.json().get("detail", {})
            errs = d.get("errors", []) if isinstance(d, dict) else []
            check("2. phase=validation", d.get("phase") == "validation", str(d))
            check("2. 错误定位到原始位置 index=1",
                  len(errs) == 1 and errs[0].get("index") == 1, str(errs))
            check("2. 错误原因指出场景不存在",
                  any("场景" in x for x in errs[0].get("reasons", [])), str(errs))
            count_after_2 = c.get(f"{base}/operations", params={"page_size": 200}).json()["total"]
            check("2. 整批零写入（总数仍为 3）", count_after_2 == 3, f"total={count_after_2}")

            # ---- 场景 3：中间一条(index=1)保存阶段异常 -> 整体回滚 ----
            # duration_ms=1e19 通过 pydantic 校验，但超出 SQLite INTEGER，flush 时抛错。
            batch_bad_save = [op("SN-20"), op("SN-21", duration_ms=10 ** 19), op("SN-22")]
            r = c.post(f"{base}/operations/batch", json=batch_bad_save)
            check("3. 保存异常批次返回 400", r.status_code == 400, f"status={r.status_code} body={r.text[:300]}")
            d = r.json().get("detail", {})
            errs = d.get("errors", []) if isinstance(d, dict) else []
            check("3. phase=save", d.get("phase") == "save", str(d))
            check("3. 错误定位到原始位置 index=1",
                  len(errs) == 1 and errs[0].get("index") == 1, str(errs))
            count_after_3 = c.get(f"{base}/operations", params={"page_size": 200}).json()["total"]
            check("3. 先前 flush 的记录一并回滚（总数仍为 3，无部分写入）",
                  count_after_3 == 3, f"total={count_after_3}")
            serials = {it["robot_serial"] for it in
                       c.get(f"{base}/operations", params={"page_size": 200}).json()["items"]}
            check("3. SN-20/SN-21/SN-22 均未落库",
                  not ({"SN-20", "SN-21", "SN-22"} & serials), str(serials))

            # ---- 场景 4a：相同载荷立即重试 -> 幂等，不重复 ----
            r = c.post(f"{base}/operations/batch", json=batch1)
            body = r.json()
            ids_retry = [it["data"]["id"] for it in body["results"]]
            check("4a. 重试返回 200 且 replayed=True",
                  r.status_code == 200 and body.get("replayed") is True, str(body))
            check("4a. 复用首次记录 ID（无新插入、无错位）", ids_retry == ids_first,
                  f"first={ids_first} retry={ids_retry}")
            count_after_4a = c.get(f"{base}/operations", params={"page_size": 200}).json()["total"]
            check("4a. 重试后总数仍为 3（无重复数据）", count_after_4a == 3, f"total={count_after_4a}")

        # ---- 场景 4b：重启服务进程后再次提交，指纹已持久化，仍幂等 ----
        stop_server(proc)
        proc = start_server(db_path, port)
        with httpx.Client(timeout=10) as c:
            r = c.post(f"{base}/operations/batch", json=batch1)
            body = r.json()
            ids_restart = [it["data"]["id"] for it in body["results"]]
            check("4b. 重启后相同提交 200 且 replayed=True",
                  r.status_code == 200 and body.get("replayed") is True, str(body))
            check("4b. 重启后仍返回首次记录 ID", ids_restart == ids_first,
                  f"first={ids_first} after_restart={ids_restart}")
            total = c.get(f"{base}/operations", params={"page_size": 200}).json()["total"]
            check("4b. 重启后重试总数仍为 3（跨重启无重复）", total == 3, f"total={total}")

            # ---- 场景 5：单条录入接口行为不变 ----
            one = op("SN-SOLO")
            r = c.post(f"{base}/operations", json=one)
            check("5. 单条录入成功(200)且不携带批次字段",
                  r.status_code == 200 and r.json().get("robot_serial") == "SN-SOLO",
                  f"status={r.status_code} body={r.text[:200]}")
            r = c.post(f"{base}/operations", json=op("SN-X", scene_id=999999))
            check("5. 单条录入关联缺失仍返回 400 机型/场景/技能错误",
                  r.status_code == 400 and ("不存在" in r.json().get("detail", "")),
                  f"status={r.status_code} body={r.text[:200]}")

    finally:
        stop_server(proc)

    failed = [n for n, ok, _ in results if not ok]
    print("\n================ 验证结果 ================")
    print(f"共 {len(results)} 项，通过 {len(results) - len(failed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：")
        for n in failed:
            print(" -", n)
        sys.exit(1)
    print("全部通过 ✔")


if __name__ == "__main__":
    main()
