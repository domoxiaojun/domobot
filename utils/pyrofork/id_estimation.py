"""
ID 推测算法模块

基于 200+ 个真实用户数据点，使用线性插值估算注册日期（月份级别精度）

数据来源：社区贡献的真实用户数据（2013-2025）
存储策略：双重保存（Redis Sorted Set + JSON 文件备份）
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 200+ 个真实数据点（2013-2025），按 ID 排序，模块加载时只排序一次
_DATA_POINTS = sorted(
    [
        (0, datetime(2013, 8, 14)),
        (2768409, datetime(2013, 11, 1)),
        (7679610, datetime(2013, 12, 31)),
        (11538514, datetime(2014, 2, 1)),
        (15835244, datetime(2014, 2, 20)),
        (23646077, datetime(2014, 2, 26)),
        (38015510, datetime(2014, 3, 1)),
        (44634663, datetime(2014, 5, 6)),
        (46145305, datetime(2014, 5, 15)),
        (54845238, datetime(2014, 9, 20)),
        (63263518, datetime(2014, 10, 27)),
        (101260938, datetime(2015, 3, 6)),
        (101323197, datetime(2015, 3, 13)),
        (111220210, datetime(2015, 4, 21)),
        (103258382, datetime(2015, 5, 27)),
        (103151531, datetime(2015, 6, 3)),
        (116812045, datetime(2015, 7, 23)),
        (122600695, datetime(2015, 7, 24)),
        (109393468, datetime(2015, 8, 8)),
        (112594714, datetime(2015, 8, 15)),
        (124872445, datetime(2015, 8, 17)),
        (130029930, datetime(2015, 9, 3)),
        (125828524, datetime(2015, 10, 5)),
        (133909606, datetime(2015, 10, 7)),
        (157242073, datetime(2015, 11, 6)),
        (143445125, datetime(2015, 12, 1)),
        (148670295, datetime(2016, 1, 8)),
        (152079341, datetime(2016, 1, 22)),
        (171295414, datetime(2016, 3, 9)),
        (181783990, datetime(2016, 4, 10)),
        (222021233, datetime(2016, 6, 8)),
        (225034354, datetime(2016, 6, 18)),
        (278941742, datetime(2016, 9, 10)),
        (285253072, datetime(2016, 10, 18)),
        (294851037, datetime(2016, 11, 19)),
        (297621225, datetime(2016, 12, 16)),
        (328594461, datetime(2017, 1, 28)),
        (337808429, datetime(2017, 2, 21)),
        (341546272, datetime(2017, 2, 22)),
        (352940995, datetime(2017, 2, 24)),
        (369669043, datetime(2017, 3, 31)),
        (400169472, datetime(2017, 7, 31)),
        (805158066, datetime(2019, 7, 15)),
        (1974255900, datetime(2021, 10, 12)),
        (5031711230, datetime(2021, 12, 6)),
        (5022636255, datetime(2021, 12, 10)),
        (5045293264, datetime(2022, 1, 13)),
        (5070164216, datetime(2022, 1, 19)),
        (5149590651, datetime(2022, 1, 22)),
        (5177789190, datetime(2022, 1, 24)),
        (5288930461, datetime(2022, 1, 27)),
        (5207110227, datetime(2022, 2, 3)),
        (5210565134, datetime(2022, 2, 9)),
        (5196353812, datetime(2022, 2, 15)),
        (5124771193, datetime(2022, 2, 22)),
        (5170390109, datetime(2022, 2, 28)),
        (5169485538, datetime(2022, 3, 1)),
        (5260388619, datetime(2022, 3, 2)),
        (5106451106, datetime(2022, 3, 5)),
        (5179102906, datetime(2022, 3, 12)),
        (5155903109, datetime(2022, 3, 22)),
        (5268253519, datetime(2022, 3, 22)),
        (5153900870, datetime(2022, 3, 22)),
        (5047148663, datetime(2022, 4, 5)),
        (5144324763, datetime(2022, 4, 6)),
        (5244529493, datetime(2022, 4, 19)),
        (5396515972, datetime(2022, 4, 21)),
        (5308260177, datetime(2022, 4, 25)),
        (5349830748, datetime(2022, 4, 29)),
        (5271530336, datetime(2022, 4, 30)),
        (5259159476, datetime(2022, 5, 6)),
        (5166844465, datetime(2022, 5, 9)),
        (5394432429, datetime(2022, 5, 23)),
        (5351497367, datetime(2022, 5, 24)),
        (5505809357, datetime(2022, 5, 27)),
        (5433708969, datetime(2022, 5, 28)),
        (5488407539, datetime(2022, 5, 29)),
        (5598262640, datetime(2022, 6, 11)),
        (5596032583, datetime(2022, 6, 16)),
        (5159326926, datetime(2022, 6, 16)),
        (5434011049, datetime(2022, 6, 29)),
        (5542245357, datetime(2022, 7, 7)),
        (5428357996, datetime(2022, 7, 11)),
        (5468950164, datetime(2022, 7, 14)),
        (5468433192, datetime(2022, 7, 20)),
        (5442755368, datetime(2022, 7, 23)),
        (5546930145, datetime(2022, 7, 24)),
        (5363536419, datetime(2022, 8, 1)),
        (5451256696, datetime(2022, 8, 6)),
        (5519218712, datetime(2022, 8, 14)),
        (5694365966, datetime(2022, 8, 28)),
        (5721138769, datetime(2022, 9, 23)),
        (5601951167, datetime(2022, 10, 2)),
        (5515826405, datetime(2022, 10, 3)),
        (5705427359, datetime(2022, 10, 6)),
        (5735455201, datetime(2022, 10, 7)),
        (5744374534, datetime(2022, 10, 10)),
        (5681900282, datetime(2022, 10, 17)),
        (5595045952, datetime(2022, 10, 23)),
        (5340744210, datetime(2022, 10, 26)),
        (5765259845, datetime(2022, 10, 30)),
        (5558980075, datetime(2022, 10, 30)),
        (5472518401, datetime(2022, 11, 2)),
        (5795660441, datetime(2022, 11, 6)),
        (5559594088, datetime(2022, 11, 10)),
        (5931294587, datetime(2022, 11, 19)),
        (5859861622, datetime(2022, 11, 19)),
        (5627539474, datetime(2022, 12, 2)),
        (5862080962, datetime(2022, 12, 13)),
        (5839137822, datetime(2022, 12, 16)),
        (5983753471, datetime(2022, 12, 23)),
        (5815100469, datetime(2022, 12, 29)),
        (5964221956, datetime(2023, 1, 9)),
        (5806925457, datetime(2023, 1, 12)),
        (5567880858, datetime(2023, 1, 25)),
        (6271031786, datetime(2023, 2, 12)),
        (6254094947, datetime(2023, 2, 27)),
        (5804028268, datetime(2023, 3, 5)),
        (6277658932, datetime(2023, 3, 17)),
        (5802659303, datetime(2023, 3, 21)),
        (5869978651, datetime(2023, 3, 24)),
        (5738347976, datetime(2023, 4, 25)),
        (5854845236, datetime(2023, 4, 27)),
        (6074830852, datetime(2023, 5, 1)),
        (5891297818, datetime(2023, 5, 4)),
        (6175817126, datetime(2023, 5, 7)),
        (6001287799, datetime(2023, 5, 10)),
        (5994561143, datetime(2023, 5, 16)),
        (6108395402, datetime(2023, 5, 18)),
        (5904140174, datetime(2023, 5, 20)),
        (6135597783, datetime(2023, 5, 24)),
        (6180394472, datetime(2023, 5, 29)),
        (6000582627, datetime(2023, 5, 30)),
        (6188508923, datetime(2023, 6, 22)),
        (6326011828, datetime(2023, 7, 7)),
        (6523424924, datetime(2023, 8, 2)),
        (6684986493, datetime(2023, 9, 25)),
        (6765129195, datetime(2023, 11, 2)),
        (6827058708, datetime(2023, 11, 6)),
        (6514802524, datetime(2023, 11, 16)),
        (6749492866, datetime(2023, 11, 22)),
        (6401027363, datetime(2023, 11, 25)),
        (6451891234, datetime(2023, 12, 2)),
        (6513268158, datetime(2023, 12, 2)),
        (6829119388, datetime(2023, 12, 2)),
        (6947316117, datetime(2023, 12, 15)),
        (6545049031, datetime(2023, 12, 19)),
        (6926984452, datetime(2024, 1, 9)),
        (6536173556, datetime(2024, 1, 11)),
        (6670760749, datetime(2024, 1, 14)),
        (6903333095, datetime(2024, 1, 31)),
        (6854829938, datetime(2024, 2, 1)),
        (6715889959, datetime(2024, 2, 5)),
        (6732829831, datetime(2024, 2, 11)),
        (6559717847, datetime(2024, 2, 25)),
        (6720229740, datetime(2024, 3, 17)),
        (6606876583, datetime(2024, 3, 17)),
        (7002435197, datetime(2024, 4, 6)),
        (7104310277, datetime(2024, 4, 19)),
        (6703731755, datetime(2024, 5, 5)),
        (7085776398, datetime(2024, 5, 10)),
        (6651640269, datetime(2024, 5, 18)),
        (6872061796, datetime(2024, 5, 25)),
        (7242296450, datetime(2024, 5, 29)),
        (7254607307, datetime(2024, 6, 10)),
        (7293965553, datetime(2024, 6, 16)),
        (7409259451, datetime(2024, 6, 20)),
        (7280136256, datetime(2024, 7, 4)),
        (7363299295, datetime(2024, 7, 25)),
        (7224009547, datetime(2024, 8, 2)),
        (7458668365, datetime(2024, 8, 2)),
        (7243375923, datetime(2024, 8, 25)),
        (7078066115, datetime(2024, 9, 8)),
        (7357703634, datetime(2024, 9, 10)),
        (7832006200, datetime(2024, 9, 19)),
        (7793034911, datetime(2024, 9, 23)),
        (7747102337, datetime(2024, 11, 6)),
        (7831448272, datetime(2024, 11, 11)),
        (7273085448, datetime(2024, 11, 21)),
        (7450316621, datetime(2024, 12, 2)),
        (7664959631, datetime(2024, 12, 19)),
        (7342300216, datetime(2025, 1, 16)),
        (7825518194, datetime(2025, 1, 16)),
        (8173852075, datetime(2025, 2, 21)),
        (8135088730, datetime(2025, 3, 5)),
        (8044853035, datetime(2025, 3, 20)),
        (7591351660, datetime(2025, 3, 21)),
        (7964511972, datetime(2025, 3, 26)),
        (7899152800, datetime(2025, 4, 8)),
        (7708562823, datetime(2025, 5, 10)),
        (7829910989, datetime(2025, 5, 11)),
        (7852083588, datetime(2025, 6, 2)),
        (7870888707, datetime(2025, 6, 8)),
        (7817256746, datetime(2025, 6, 18)),
        (7915901421, datetime(2025, 7, 7)),
        (8179125032, datetime(2025, 7, 9)),
        (8238766847, datetime(2025, 7, 31)),
        (8343786378, datetime(2025, 8, 8)),
        (8369442459, datetime(2025, 8, 8)),
        (8096742229, datetime(2025, 8, 31)),
        (7834356221, datetime(2025, 9, 1)),
        (8461579295, datetime(2025, 9, 11)),
        (8200159552, datetime(2025, 9, 12)),
        (7912577935, datetime(2025, 9, 15)),
        (8017192943, datetime(2025, 10, 5)),
        (8325327280, datetime(2025, 10, 13)),
        (8117852491, datetime(2025, 10, 14)),
        (8384648263, datetime(2025, 10, 23)),
        (8393200797, datetime(2025, 10, 25)),
        (8209194945, datetime(2025, 10, 26)),
        (8480708838, datetime(2025, 11, 5)),
        (8559682245, datetime(2025, 11, 11)),
    ],
    key=lambda x: x[0],
)


async def estimate_registration_date(user_id: int) -> datetime | None:
    """
    根据用户 ID 估算注册日期（使用 200+ 个真实数据点）

    数据来源：社区贡献的真实用户数据（2013-2025）
    精度：月份级别

    Args:
        user_id: 用户 ID

    Returns:
        估算的注册日期，如果无法估算则返回 None
    """
    data_points = _DATA_POINTS

    # 找到合适的区间进行线性插值
    for i in range(len(data_points) - 1):
        id1, date1 = data_points[i]
        id2, date2 = data_points[i + 1]

        if id1 <= user_id < id2:
            # 线性插值
            ratio = (user_id - id1) / (id2 - id1)
            time_diff = (date2 - date1).total_seconds()
            estimated_seconds = date1.timestamp() + (time_diff * ratio)
            return datetime.fromtimestamp(estimated_seconds)

    # 边界情况处理
    if user_id < data_points[0][0]:
        # ID 小于最小数据点，返回最早日期
        return data_points[0][1]

    # ID 大于等于最大数据点，基于最后一个点外推
    last_id, last_date = data_points[-1]
    # 假设每月新增约 30,000,000 个 ID（基于 2025 年的增长速度）
    days_since = (user_id - last_id) / 1000000  # 粗略估算
    return last_date + timedelta(days=days_since)


async def save_registration_sample(
    redis_client, user_id: int, registration_date: datetime
) -> bool:
    """
    保存用户 ID 和注册日期到样本数据集，用于改进 estimate_registration_date() 算法

    双重保存策略：
    1. Redis Sorted Set (实时查询)
    2. JSON 文件 (持久化备份)

    Redis 存储：
    - Key: "registration_samples"
    - Member: user_id (字符串)
    - Score: registration_date (Unix 时间戳)

    JSON 文件：
    - 路径: data/registration_samples.json
    - 格式: [{"user_id": 123, "registration_date": "2025-11-01T00:00:00", "saved_at": "2025-11-04T01:30:00"}, ...]

    Args:
        redis_client: Redis 客户端
        user_id: 用户 ID
        registration_date: 注册日期

    Returns:
        bool: 保存是否成功
    """
    success = True

    try:
        # 1. 保存到 Redis Sorted Set（member=user_id 保证唯一，score=时间戳可排序）
        await redis_client.zadd(
            "registration_samples",
            {str(user_id): registration_date.timestamp()},
        )
        logger.debug(f"✅ Redis: 已保存样本 user_id={user_id}")

    except Exception as e:
        logger.error(f"❌ Redis: 保存样本失败: {e}")
        success = False

    try:
        # 2. 保存到 JSON 文件 (存储在 data/ 目录)
        json_file_path = Path("data/registration_samples.json")

        # 确保目录存在
        json_file_path.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有数据
        samples = []
        if json_file_path.exists():
            try:
                with open(json_file_path, "r", encoding="utf-8") as f:
                    samples = json.load(f)
            except json.JSONDecodeError:
                logger.warning("JSON 文件格式错误,将重新创建")
                samples = []

        # 检查是否已存在该用户的样本
        existing_index = None
        for i, sample in enumerate(samples):
            if sample.get("user_id") == user_id:
                existing_index = i
                break

        # 构造新样本数据
        new_sample = {
            "user_id": user_id,
            "registration_date": registration_date.isoformat(),
            "saved_at": datetime.now().isoformat(),
        }

        # 更新或添加样本
        if existing_index is not None:
            samples[existing_index] = new_sample
            logger.debug(f"✅ JSON: 已更新样本 user_id={user_id}")
        else:
            samples.append(new_sample)
            logger.debug(f"✅ JSON: 已添加样本 user_id={user_id}")

        # 按 user_id 排序
        samples.sort(key=lambda x: x["user_id"])

        # 保存到文件
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)

        logger.info(
            f"📊 已将用户 {user_id} 的注册时间 ({registration_date.strftime('%Y年%m月')}) "
            f"保存到 ID-时间映射表 (总样本数: {len(samples)})"
        )

    except Exception as e:
        logger.error(f"❌ JSON: 保存样本失败: {e}", exc_info=True)
        success = False

    return success
