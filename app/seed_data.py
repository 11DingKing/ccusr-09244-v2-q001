import sys
import os
import random
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app.models import (
    RobotModel, Scene, Skill, OperationData, Annotation,
    Dataset, DatasetItem, DatasetReuse
)


def init_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("数据库表已创建")


def seed_data():
    db = SessionLocal()
    try:
        robot_models_data = [
            {
                "name": "RM-65A",
                "manufacturer": "RealMotion",
                "description": "六轴协作机械臂，负载6.5kg，适用于电子装配和精密抓取场景",
                "capabilities": {
                    "payload_kg": 6.5,
                    "reach_mm": 920,
                    "repeatability_mm": 0.02,
                    "axes": 6,
                    "features": ["力控", "视觉引导", "碰撞检测"]
                }
            },
            {
                "name": "RM-12B",
                "manufacturer": "RealMotion",
                "description": "重载工业机械臂，负载12kg，适用于汽车零部件和重型搬运",
                "capabilities": {
                    "payload_kg": 12,
                    "reach_mm": 1450,
                    "repeatability_mm": 0.05,
                    "axes": 6,
                    "features": ["高速", "重载", "防尘防水IP67"]
                }
            },
            {
                "name": "RM-Foodie",
                "manufacturer": "RealMotion",
                "description": "餐饮服务机器人，食品级材质，适用于餐饮零售场景",
                "capabilities": {
                    "payload_kg": 3,
                    "reach_mm": 700,
                    "repeatability_mm": 0.1,
                    "axes": 4,
                    "features": ["食品级", "易清洁", "轻量"]
                }
            }
        ]

        robot_models = []
        for rm_data in robot_models_data:
            rm = RobotModel(**rm_data)
            db.add(rm)
            robot_models.append(rm)
        db.flush()

        scenes_data = [
            {
                "name": "PCB电子装配线",
                "category": "生产制造",
                "description": "电子工厂SMT后段PCB插件与装配工位，存在一定粉尘",
                "environment_tags": ["室内", "有粉尘", "恒温", "静电防护"]
            },
            {
                "name": "汽车零部件焊接车间",
                "category": "生产制造",
                "description": "汽车底盘和车身零部件焊接，温差大、有焊接烟尘",
                "environment_tags": ["室内", "高温差", "焊接烟尘", "强电磁干扰"]
            },
            {
                "name": "物流仓储分拣区",
                "category": "生产制造",
                "description": "电商仓储包裹分拣，环境温度变化较大",
                "environment_tags": ["室内", "温差大", "人员流动大"]
            },
            {
                "name": "连锁餐厅后厨配菜",
                "category": "餐饮零售",
                "description": "中央厨房式连锁餐饮后厨，高温高湿、有油烟",
                "environment_tags": ["室内", "高温高湿", "油烟", "食品环境"]
            },
            {
                "name": "奶茶店吧台饮品制作",
                "category": "餐饮零售",
                "description": "连锁奶茶门店饮品制作操作台，温差变化大",
                "environment_tags": ["室内", "温差大", "潮湿", "客户接触"]
            },
            {
                "name": "便利店货架理货",
                "category": "餐饮零售",
                "description": "24小时便利店商品上架与理货",
                "environment_tags": ["室内", "常温", "照明充足", "小空间"]
            }
        ]

        scenes = []
        for s_data in scenes_data:
            s = Scene(**s_data)
            db.add(s)
            scenes.append(s)
        db.flush()

        skills_data = [
            {"name": "精密抓取", "category": "操作", "description": "对小尺寸零件的高精度抓取与放置"},
            {"name": "螺丝锁付", "category": "装配", "description": "自动螺丝拧紧与扭矩控制"},
            {"name": "焊接作业", "category": "加工", "description": "弧焊和点焊作业轨迹控制"},
            {"name": "搬运码垛", "category": "物流", "description": "物品搬运与码放堆叠"},
            {"name": "取餐送餐", "category": "服务", "description": "餐品从厨房到餐桌的取送"},
            {"name": "饮品调制", "category": "服务", "description": "按配方进行饮品原料配比与调制"},
            {"name": "货架理货", "category": "服务", "description": "商品识别与货架补货"}
        ]

        skills = []
        for sk_data in skills_data:
            sk = Skill(**sk_data)
            db.add(sk)
            skills.append(sk)
        db.flush()

        print(f"已创建 {len(robot_models)} 种机型, {len(scenes)} 种场景, {len(skills)} 种技能")

        robot_scene_skill_map = {
            robot_models[0].id: [
                (scenes[0].id, skills[0].id),
                (scenes[0].id, skills[1].id),
                (scenes[2].id, skills[3].id),
            ],
            robot_models[1].id: [
                (scenes[1].id, skills[2].id),
                (scenes[2].id, skills[3].id),
            ],
            robot_models[2].id: [
                (scenes[3].id, skills[4].id),
                (scenes[4].id, skills[5].id),
                (scenes[5].id, skills[6].id),
            ]
        }

        failure_categories = [
            ("感知异常", "视觉识别失败"),
            ("感知异常", "深度传感器异常"),
            ("感知异常", "目标丢失"),
            ("感知异常", "光照不足"),
            ("运动控制异常", "轨迹偏差超限"),
            ("运动控制异常", "碰撞检测触发"),
            ("抓取异常", "抓取力不足"),
            ("抓取异常", "物体滑脱"),
            ("抓取异常", "姿态错误"),
            ("环境干扰", "粉尘干扰"),
            ("环境干扰", "温度异常"),
            ("环境干扰", "振动干扰"),
            ("硬件故障", "通信中断"),
            ("其他", "未知错误"),
        ]

        operation_data_list = []
        annotation_list = []

        total_ops = 150
        start_date = datetime(2026, 1, 1)

        random.seed(42)

        for i in range(total_ops):
            rm_id = random.choice(list(robot_scene_skill_map.keys()))
            s_id, sk_id = random.choice(robot_scene_skill_map[rm_id])

            start_time = start_date + timedelta(
                days=random.randint(0, 165),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
            duration = random.randint(2000, 30000)
            end_time = start_time + timedelta(milliseconds=duration)

            num_waypoints = random.randint(5, 30)
            waypoints = []
            for w in range(num_waypoints):
                waypoints.append({
                    "x": round(random.uniform(-200, 200), 2),
                    "y": round(random.uniform(-150, 150), 2),
                    "z": round(random.uniform(0, 500), 2),
                    "rx": round(random.uniform(-3.14, 3.14), 3),
                    "ry": round(random.uniform(-3.14, 3.14), 3),
                    "rz": round(random.uniform(-3.14, 3.14), 3),
                    "time_ms": int(w * (duration / num_waypoints))
                })

            joint_angles = []
            for w in range(num_waypoints):
                joint_angles.append([round(random.uniform(-180, 180), 2) for _ in range(6)])

            motion_trajectory = {
                "waypoints": waypoints,
                "joint_angles": joint_angles,
                "tool_speed_mm_s": round(random.uniform(50, 500), 2),
                "max_force_n": round(random.uniform(5, 80), 2) if random.random() > 0.3 else None
            }

            perception_records_data = {
                "camera_images_captured": random.randint(3, 20),
                "depth_frames": random.randint(5, 30),
                "detections": [
                    {
                        "object_id": f"obj-{idx}",
                        "class": random.choice(["零件A", "零件B", "包装盒", "餐具", "食材"]),
                        "confidence": round(random.uniform(0.6, 0.99), 3),
                        "bbox_3d": {
                            "x": round(random.uniform(-100, 100), 2),
                            "y": round(random.uniform(-100, 100), 2),
                            "z": round(random.uniform(0, 300), 2),
                            "w": round(random.uniform(10, 100), 1),
                            "h": round(random.uniform(10, 100), 1),
                            "d": round(random.uniform(10, 100), 1)
                        }
                    }
                    for idx in range(random.randint(1, 5))
                ],
                "tactile_readings": [round(random.uniform(0, 5), 2) for _ in range(10)] if random.random() > 0.4 else None
            }

            is_success = random.random() > 0.25

            grasp_result = None
            if random.random() > 0.2:
                grasp_result = {
                    "attempted": True,
                    "success": is_success,
                    "grasp_force_n": round(random.uniform(5, 60), 2),
                    "contact_points": random.randint(2, 4),
                    "slippage_detected": not is_success and random.random() > 0.5,
                    "object_pose_after": {
                        "x": round(random.uniform(-100, 100), 2),
                        "y": round(random.uniform(-100, 100), 2),
                        "z": round(random.uniform(0, 300), 2)
                    } if is_success else None
                }

            scene = next(s for s in scenes if s.id == s_id)
            env_conditions = {}
            if "有粉尘" in (scene.environment_tags or []):
                env_conditions["dust_pm25_ugm3"] = random.randint(20, 150)
            if "高温差" in (scene.environment_tags or []):
                env_conditions["temperature_c"] = round(random.uniform(10, 45), 1)
                env_conditions["humidity_rh"] = round(random.uniform(30, 90), 1)
            if "焊接烟尘" in (scene.environment_tags or []):
                env_conditions["fume_level"] = random.choice(["低", "中", "高"])
            if "油烟" in (scene.environment_tags or []):
                env_conditions["oil_fume_level"] = random.choice(["低", "中", "高"])
                env_conditions["temperature_c"] = round(random.uniform(25, 50), 1)
            env_conditions["ambient_light_lux"] = random.randint(100, 1000)

            hw_status = {
                "joint_temperatures_c": [round(random.uniform(25, 65), 1) for _ in range(6)],
                "cpu_usage_percent": random.randint(15, 85),
                "battery_level_percent": random.randint(20, 100),
                "servo_errors": [] if random.random() > 0.1 else ["关节2轻微过载"]
            }

            serial_numbers = {
                robot_models[0].id: ["RM65A-2025-001", "RM65A-2025-002", "RM65A-2025-003"],
                robot_models[1].id: ["RM12B-2025-001", "RM12B-2025-002"],
                robot_models[2].id: ["RMFD-2025-001", "RMFD-2025-002", "RMFD-2025-003", "RMFD-2025-004"]
            }

            op = OperationData(
                robot_model_id=rm_id,
                scene_id=s_id,
                skill_id=sk_id,
                robot_serial=random.choice(serial_numbers[rm_id]),
                motion_trajectory=motion_trajectory,
                perception_records=perception_records_data,
                grasp_result=grasp_result,
                timestamp_start=start_time,
                timestamp_end=end_time,
                duration_ms=duration,
                environment_conditions=env_conditions if env_conditions else None,
                hardware_status=hw_status
            )
            operation_data_list.append(op)

        db.bulk_save_objects(operation_data_list)
        db.flush()

        all_ops = db.query(OperationData).all()
        op_ids = [op.id for op in all_ops]

        random.shuffle(op_ids)
        ops_to_annotate = op_ids[: int(len(op_ids) * 0.82)]

        annotators = ["张工", "李工", "王工", "赵工", "陈工", "刘工"]
        reviewers = ["复核-甲", "复核-乙", "复核-丙"]

        for idx, op_id in enumerate(ops_to_annotate):
            op = db.query(OperationData).filter(OperationData.id == op_id).first()
            if not op:
                continue

            gr = op.grasp_result or {}
            is_success = gr.get("success", random.random() > 0.25)

            failure_cat = None
            failure_subcat = None
            failure_desc = None

            if not is_success:
                fc, fsc = random.choice(failure_categories)
                failure_cat = fc
                failure_subcat = fsc
                desc_map = {
                    "视觉识别失败": "粉尘覆盖镜头导致目标零件识别率低于阈值",
                    "深度传感器异常": "温差导致深度数据噪点过多",
                    "目标丢失": "作业过程中目标被遮挡后重新识别失败",
                    "光照不足": "车间照明不稳定，识别时亮度过低",
                    "轨迹偏差超限": "振动导致末端执行器轨迹超出±0.5mm容差",
                    "碰撞检测触发": "与工装夹具发生轻微碰撞，安全系统触发停止",
                    "抓取力不足": "接触面有油污，摩擦力不足",
                    "物体滑脱": "加速阶段物体从夹爪中滑落",
                    "姿态错误": "物体姿态与预期偏差超过15度",
                    "粉尘干扰": "传感器表面积尘，感知数据异常",
                    "温度异常": "环境温度过高导致关节性能下降",
                    "振动干扰": "邻近设备运行产生共振",
                    "通信中断": "电磁干扰导致控制器与服务器通信超时",
                    "未知错误": "多因素综合导致，待进一步分析"
                }
                failure_desc = desc_map.get(fsc, fsc)

            review_roll = random.random()
            if review_roll < 0.5:
                review_status = "approved"
            elif review_roll < 0.75:
                review_status = "pending"
            else:
                review_status = "rejected"

            annotation = Annotation(
                operation_data_id=op_id,
                is_success=is_success,
                failure_category=failure_cat,
                failure_subcategory=failure_subcat,
                failure_description=failure_desc,
                annotator=random.choice(annotators),
                review_status=review_status,
                reviewer=random.choice(reviewers) if review_status != "pending" else None,
                review_notes="标注准确，数据完整" if review_status == "approved" else (
                    "失败分类需要进一步确认" if review_status == "rejected" else None
                ),
                annotation_quality_score=round(random.uniform(0.7, 1.0), 3) if review_status == "approved" else (
                    round(random.uniform(0.4, 0.7), 3) if review_status == "pending" else round(random.uniform(0.2, 0.5), 3)
                )
            )
            annotation_list.append(annotation)

        db.bulk_save_objects(annotation_list)
        db.flush()

        print(f"已创建 {len(operation_data_list)} 条作业数据, {len(annotation_list)} 条标注记录")

        datasets_config = [
            {
                "name": "RM-65A PCB精密抓取数据集_v1.2",
                "description": "PCB装配场景小零件精密抓取作业，包含完整的轨迹、视觉和力控数据，适合用于抓取策略训练",
                "version": "1.2",
                "rm_idx": 0,
                "scene_idx": 0,
                "skill_idx": 0,
                "owner_team": "精密装配组",
                "contact_person": "张工",
                "is_published": True,
                "tags": ["精密抓取", "电子装配", "粉尘环境", "高价值"],
                "license_info": "内部使用许可v2.0",
                "reuses": [
                    ("视觉算法组", "抓取检测模型微调", "PCB-Auto项目"),
                    ("强化学习组", "抓取策略优化", "Dexterity项目"),
                ]
            },
            {
                "name": "RM-65A 螺丝锁付数据集_v1.0",
                "description": "多种规格螺丝的自动锁付作业，含扭矩控制数据和失败案例",
                "version": "1.0",
                "rm_idx": 0,
                "scene_idx": 0,
                "skill_idx": 1,
                "owner_team": "精密装配组",
                "contact_person": "李工",
                "is_published": True,
                "tags": ["螺丝锁付", "扭矩控制", "装配"],
                "license_info": "内部使用许可v2.0",
                "reuses": [
                    ("控制算法组", "力控参数优化", "ScrewMaster项目"),
                ]
            },
            {
                "name": "RM-12B 汽车零部件焊接数据集_v2.1",
                "description": "高温差高粉尘车间焊接作业数据，包含多种焊接缺陷标注，是鲁棒性训练的优质数据集",
                "version": "2.1",
                "rm_idx": 1,
                "scene_idx": 1,
                "skill_idx": 2,
                "owner_team": "焊接工艺组",
                "contact_person": "王工",
                "is_published": True,
                "tags": ["焊接", "高温差", "烟尘环境", "汽车制造"],
                "license_info": "内部使用许可v2.0",
                "reuses": [
                    ("焊接工艺组", "焊接参数自适应", "AutoWeld项目"),
                    ("视觉组", "烟尘环境下焊缝识别", "SmokeEye项目"),
                    ("控制算法组", "热变形补偿", "ThermalComp项目"),
                    ("复核组", "焊接缺陷检测", "WeldCheck项目"),
                ]
            },
            {
                "name": "RM-Foodie 餐厅后厨取餐数据集_v1.0",
                "description": "餐饮环境下餐品识别与抓取，高温高湿油烟场景，覆盖多种餐具和餐品类型",
                "version": "1.0",
                "rm_idx": 2,
                "scene_idx": 3,
                "skill_idx": 4,
                "owner_team": "服务机器人组",
                "contact_person": "赵工",
                "is_published": True,
                "tags": ["餐饮", "食品级", "高温高湿", "服务机器人"],
                "license_info": "内部使用许可v2.0",
                "reuses": [
                    ("产品一部", "连锁餐厅部署", "FoodBot-X项目"),
                ]
            },
            {
                "name": "RM-Foodie 奶茶饮品调制数据集_v1.5",
                "description": "吧台饮品制作全流程，含液体倾倒、配料抓取、摇杯等动作数据",
                "version": "1.5",
                "rm_idx": 2,
                "scene_idx": 4,
                "skill_idx": 5,
                "owner_team": "服务机器人组",
                "contact_person": "陈工",
                "is_published": False,
                "tags": ["餐饮", "饮品调制", "液体操作"],
                "license_info": "内部使用许可v2.0",
                "reuses": []
            },
            {
                "name": "物流搬运抗干扰数据集_v1.0",
                "description": "多机型混合场景，温差和人员干扰下的搬运码垛作业数据",
                "version": "1.0",
                "rm_idx": 0,
                "scene_idx": 2,
                "skill_idx": 3,
                "owner_team": "物流自动化组",
                "contact_person": "刘工",
                "is_published": True,
                "tags": ["物流", "搬运", "人员干扰", "鲁棒性"],
                "license_info": "内部使用许可v2.0",
                "reuses": [
                    ("安全系统组", "人机协作避障", "SafeMate项目"),
                ]
            }
        ]

        created_datasets = []
        for ds_cfg in datasets_config:
            rm = robot_models[ds_cfg["rm_idx"]]
            s = scenes[ds_cfg["scene_idx"]]
            sk = skills[ds_cfg["skill_idx"]]

            dataset = Dataset(
                name=ds_cfg["name"],
                description=ds_cfg["description"],
                version=ds_cfg["version"],
                robot_model_id=rm.id,
                scene_id=s.id,
                skill_id=sk.id,
                owner_team=ds_cfg["owner_team"],
                contact_person=ds_cfg["contact_person"],
                is_published=ds_cfg["is_published"],
                published_at=datetime.utcnow() if ds_cfg["is_published"] else None,
                tags=ds_cfg["tags"],
                license_info=ds_cfg["license_info"]
            )
            db.add(dataset)
            db.flush()

            matched_ops = db.query(OperationData).filter(
                OperationData.robot_model_id == rm.id,
                OperationData.scene_id == s.id,
                OperationData.skill_id == sk.id
            ).all()

            ds_items = []
            num_items = min(len(matched_ops), random.randint(20, 45))
            selected = random.sample(matched_ops, num_items) if len(matched_ops) > num_items else matched_ops
            for op in selected:
                ds_items.append(DatasetItem(dataset_id=dataset.id, operation_data_id=op.id))
            db.bulk_save_objects(ds_items)

            dataset_items_all = db.query(DatasetItem).filter(DatasetItem.dataset_id == dataset.id).all()
            op_ids_in_ds = [di.operation_data_id for di in dataset_items_all]
            dataset.total_items = len(op_ids_in_ds)

            if op_ids_in_ds:
                annotations = db.query(Annotation).filter(Annotation.operation_data_id.in_(op_ids_in_ds)).all()
                success_count = sum(1 for a in annotations if a.is_success)
                failure_count = sum(1 for a in annotations if not a.is_success)
                dataset.success_count = success_count
                dataset.failure_count = failure_count
                dataset.annotation_complete_rate = len(annotations) / len(op_ids_in_ds) if op_ids_in_ds else 0.0

                quality_scores = []
                ops_in_ds = db.query(OperationData).filter(OperationData.id.in_(op_ids_in_ds)).all()
                for op in ops_in_ds:
                    if op.quality_score is not None:
                        quality_scores.append(op.quality_score)
                dataset.average_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else None

            dataset.reuse_count = len(ds_cfg["reuses"])
            created_datasets.append((dataset, ds_cfg["reuses"]))

        db.flush()

        for dataset, reuses in created_datasets:
            for team, purpose, project in reuses:
                reuse = DatasetReuse(
                    dataset_id=dataset.id,
                    reusing_team=team,
                    purpose=purpose,
                    project_name=project,
                    reuse_date=datetime.utcnow() - timedelta(days=random.randint(5, 120)),
                    notes=f"通过 {purpose} 提升了模型在真实场景下的鲁棒性"
                )
                db.add(reuse)

        db.commit()
        print(f"已创建 {len(created_datasets)} 个数据集及其复用记录")

        from app.routers.analytics import calculate_completeness_score, determine_grade

        all_ops = db.query(OperationData).all()
        thresholds = {"grade_a": 0.9, "grade_b": 0.7, "grade_c": 0.5}
        for op in all_ops:
            completeness = calculate_completeness_score(op)
            op.completeness_score = round(completeness, 4)

            annotation_quality = 0.0
            if op.annotation:
                ann = op.annotation
                base = 0.6
                if ann.review_status == "approved":
                    base += 0.2
                if ann.annotation_quality_score is not None:
                    base = ann.annotation_quality_score
                elif ann.failure_category and ann.failure_description:
                    base += 0.2
                annotation_quality = min(1.0, base)

            quality_score = (completeness * 0.5 + annotation_quality * 0.5)
            op.quality_score = round(quality_score, 4)
            op.data_grade = determine_grade(quality_score, thresholds)

        for dataset in db.query(Dataset).all():
            items = db.query(DatasetItem).filter(DatasetItem.dataset_id == dataset.id).all()
            op_ids_in_ds = [di.operation_data_id for di in items]
            if op_ids_in_ds:
                ops = db.query(OperationData).filter(OperationData.id.in_(op_ids_in_ds)).all()
                grade_counts = {}
                for op in ops:
                    if op.data_grade:
                        grade_counts[op.data_grade] = grade_counts.get(op.data_grade, 0) + 1
                if grade_counts:
                    dataset.data_grade = max(grade_counts, key=grade_counts.get)

        db.commit()
        print("已完成所有数据质量分级")
        print("\n===== 示例数据初始化完成！=====")

    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_data()
