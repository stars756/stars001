import io
import random

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw

from baykeshop.contrib.member.models import BaykeShopUser
from baykeshop.contrib.shop.models import (
    BaykeShopBrand,
    BaykeShopCategory,
    BaykeShopGoods,
    BaykeShopGoodsImages,
    BaykeShopGoodsSKU,
    BaykeShopSpec,
)

User = get_user_model()


def _make_placeholder_image(name="placeholder", size=(800, 800)):
    """Create a colored placeholder image with text overlay."""
    r, g, b = random.randint(50, 200), random.randint(50, 200), random.randint(50, 200)
    img = Image.new("RGB", size, (r, g, b))
    draw = ImageDraw.Draw(img)
    try:
        bbox = draw.textbbox((0, 0), name)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(name)
    draw.text(((size[0] - tw) / 2, (size[1] - th) / 2), name, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name=f"{name[:30]}.png")


# ── Categories ────────────────────────────────────────────────────
CATEGORIES = {
    "电脑办公": {
        "is_nav": True,
        "children": ["电脑整机", "电脑配件", "办公设备"],
    },
    "手机数码": {
        "is_nav": True,
        "children": ["智能手机", "数码配件"],
    },
    "家用电器": {
        "is_nav": True,
        "children": ["生活电器", "厨房电器", "个护健康"],
    },
    "服饰鞋包": {
        "is_nav": False,
        "children": ["男装", "女装", "鞋靴"],
    },
    "图书音像": {
        "is_nav": False,
        "children": ["文学小说", "教育考试"],
    },
}

# ── Brands ─────────────────────────────────────────────────────────
BRANDS = ["华为", "小米", "联想", "苹果", "海尔"]

# ── Specs ──────────────────────────────────────────────────────────
SPEC_GROUPS = {
    "颜色": ["红色", "蓝色", "黑色", "白色", "金色"],
    "尺寸": ["S", "M", "L", "XL", "XXL"],
    "容量": ["128G", "256G", "512G", "1T"],
    "版本": ["标准版", "尊享版", "青春版"],
}

# ── Product templates ─────────────────────────────────────────────
PRODUCT_TEMPLATES = {
    "电脑整机": [
        ("ThinkPad X1 Carbon", "联想商务轻薄本"),
        ("MacBook Pro 14", "苹果专业笔记本电脑"),
        ("MateBook X Pro", "华为旗舰轻薄本"),
        ("RedmiBook 16", "小米高性能笔记本"),
        ("拯救者Y9000P", "联想电竞游戏本"),
        ("MacBook Air M3", "苹果超轻薄笔记本"),
        ("MateBook 14", "华为全面屏笔记本"),
        ("ThinkBook 16+", "联想商务高性能本"),
        ("小米笔记本Pro", "小米高性能轻薄本"),
        ("MagicBook Pro 16", "荣耀性能创作本"),
        ("灵越14 Plus", "戴尔高性能轻薄本"),
        ("战66六代", "惠普商务办公本"),
        ("天选4", "华硕电竞游戏本"),
        ("非凡Go 14", "宏碁轻薄创作本"),
        ("MateBook D 16", "华为大屏办公本"),
        ("拯救者Y7000P", "联想入门电竞本"),
        ("MacBook Pro 16", "苹果专业移动工作站"),
        ("ThinkPad X1 Nano", "联想极致轻薄本"),
        ("Redmi G 2025", "小米游戏本"),
        ("灵耀14 2025", "华硕商务轻薄本"),
    ],
    "电脑配件": [
        ("GeForce RTX 4070", "高性能独立显卡"),
        ("酷睿i7-14700K", "英特尔高端处理器"),
        ("Ryzen 7 7800X3D", "AMD 游戏处理器"),
        ("三星990 Pro 2T", "高端NVMe固态硬盘"),
        ("海盗船DDR5 32G", "高频内存套装"),
        ("ROG STRIX Z790", "华硕旗舰主板"),
        ("酷冷至尊MB520", "中塔机箱"),
        ("海韵FOCUS GX850", "金牌全模组电源"),
        ("利民PA120 SE", "双塔风冷散热器"),
        ("LG 27GP95R", "4K 160Hz电竞显示器"),
        ("三星 49寸曲面屏", "超宽带鱼屏显示器"),
        ("ROG 龙神 III 360", "一体式水冷散热器"),
        ("金士顿 KC3000 1T", "PCIe 4.0 固态硬盘"),
        ("芝奇 皇家戟 32G", "RGB 高频内存"),
        ("微星 MPG Z790 CARBON", "暗黑系列主板"),
        ("安钛克 P10C", "静音机箱"),
        ("振华 LEPA G1000", "1000W 钛金电源"),
        ("猫头鹰 NH-D15", "旗舰风冷散热器"),
        ("华硕 TUF RTX 4060", "中高端游戏显卡"),
        ("戴尔 S2722QC", "4K 办公显示器"),
    ],
    "办公设备": [
        ("HP LaserJet Pro M404", "黑白激光打印机"),
        ("爱普生L3256", "彩色墨仓式打印机"),
        ("奔图P2506", "经济型黑白打印机"),
        ("得力M2000", "多功能一体机"),
        ("兄弟DCP-B7535DW", "无线自动双面打印机"),
        ("华为路由AX6", "千兆WiFi 6路由器"),
        ("小米路由器AX6000", "6000M速率旗舰路由"),
        ("TP-Link AX3000", "入门级WiFi 6路由"),
        ("华硕AX86U Pro", "电竞路由"),
        ("新华三NX54", "企业级家用路由"),
    ],
    "智能手机": [
        ("iPhone 16 Pro Max", "苹果旗舰手机"),
        ("Mate 70 Pro", "华为旗舰手机"),
        ("小米15 Ultra", "小米影像旗舰"),
        ("Find X8 Pro", "OPPO 旗舰手机"),
        ("vivo X200 Pro", "vivo 影像旗舰"),
        ("三星S25 Ultra", "三星安卓机皇"),
        ("荣耀Magic7 Pro", "荣耀全能旗舰"),
        ("一加13", "一加性能旗舰"),
        ("iQOO 15", "vivo 子品牌性能机"),
        ("Redmi K80 Pro", "小米子品牌旗舰"),
        ("iPhone 16", "苹果标准版手机"),
        ("华为Pura 80 Pro", "华为影像旗舰"),
        ("小米15", "小米标准旗舰"),
        ("OPPO Reno13 Pro", "OPPO 时尚手机"),
        ("vivo S20 Pro", "vivo 人像手机"),
        ("真我GT7 Pro", "真我性能旗舰"),
        ("荣耀X60 Pro", "荣耀千元机皇"),
        ("魅族21 Pro", "魅族旗舰回归"),
        ("努比亚Z80 Ultra", "屏下摄像头旗舰"),
        ("摩托罗拉Razr 60", "折叠屏手机"),
    ],
    "数码配件": [
        ("AirPods Pro 3", "苹果降噪耳机"),
        ("华为FreeBuds Pro 4", "华为旗舰耳机"),
        ("小米Buds 5 Pro", "小米高端耳机"),
        ("索尼XM6", "索尼降噪耳机"),
        ("Beats Studio Buds+", "Beats 入耳式耳机"),
        ("Anker GaN 100W", "氮化镓快充头"),
        ("小米67W快充头", "小米快充套装"),
        ("三星45W快充头", "三星超快充"),
        ("倍思100W数据线", "100W快充数据线"),
        ("绿联拓展坞9合1", "Type-C 多功能拓展坞"),
    ],
    "生活电器": [
        ("米家空气净化器5 Pro", "小米旗舰净化器"),
        ("戴森V15 Detect", "戴森旗舰吸尘器"),
        ("科沃斯X5 Pro", "扫地机器人旗舰"),
        ("石头G20", "自清洁扫拖机器人"),
        ("米家加湿器Pro", "智能恒湿加湿器"),
        ("美的风扇SAF30AC", "落地静音风扇"),
        ("格力除湿机DH40EF", "40L大容量除湿"),
        ("戴森HP09", "空气净化暖风扇"),
        ("小米空气炸锅Pro", "6.5L大容量炸锅"),
        ("飞利浦加湿器HU4816", "纳米级加湿"),
    ],
    "厨房电器": [
        ("美的微波炉M1-L213C", "家用微波炉"),
        ("格兰仕G90F25CN3L", "光波微波炉"),
        ("九阳K60", "0涂层电饭煲"),
        ("苏泊尔SF40FC996", "球釜电饭煲"),
        ("美的空气炸锅KZC6502", "6.5L大容量"),
        ("飞利浦HD9860", "空气炸锅旗舰款"),
        ("松下NN-DS2200", "蒸烤一体机"),
        ("老板60D1S", "大吸力油烟机"),
        ("方太JCD10TB", "侧吸油烟机"),
        ("小米电磁炉N1", "简约电磁炉"),
    ],
    "个护健康": [
        ("飞利浦S9000", "旗舰电动剃须刀"),
        ("博朗9系Pro", "德国进口剃须刀"),
        ("飞科FS968", "国产性价比剃须刀"),
        ("松下EW-DJ40", "冲牙器"),
        ("飞利浦HX9999", "钻石智能牙刷"),
        ("小米C1", "声波电动牙刷"),
        ("Usmile Y20", "国产旗舰电动牙刷"),
        ("松下EH-XS800", "美容仪"),
        ("雅萌ACE五代", "射频美容仪"),
        ("SKG G7 Pro", "颈部按摩仪"),
    ],
    "男装": [
        ("Pure Cotton 白衬衫", "经典商务白衬衫"),
        ("羊毛混纺西装外套", "轻奢商务西装"),
        ("休闲针织Polo衫", "纯棉珠地Polo"),
        ("弹力牛仔裤", "经典直筒牛仔裤"),
        ("轻薄羽绒服", "90白鹅绒羽绒服"),
        ("桑蚕丝领带", "商务正装领带"),
        ("商务休闲皮鞋", "头层牛皮皮鞋"),
        ("纯棉圆领T恤", "基础打底T恤"),
        ("休闲卡其裤", "修身九分卡其裤"),
        ("连帽卫衣", "加绒保暖卫衣"),
    ],
    "女装": [
        ("雪纺碎花连衣裙", "法式碎花连衣裙"),
        ("羊毛双面呢大衣", "中长款毛呢外套"),
        ("真丝衬衫", "100%桑蚕丝衬衫"),
        ("高腰阔腿裤", "垂感西裝阔腿裤"),
        ("针织开衫", "羊绒混纺开衫"),
        ("A字半身裙", "高腰显瘦A字裙"),
        ("方领泡泡袖上衣", "法式方领上衣"),
        ("蕾丝打底衫", "立领镂空蕾丝衫"),
        ("运动休闲卫衣", "宽松情侣卫衣"),
        ("风衣外套", "中长款系带风衣"),
    ],
    "鞋靴": [
        ("经典帆布鞋", "高帮帆布鞋"),
        ("运动跑鞋", "网面透气跑鞋"),
        ("真皮短靴", "切尔西短靴"),
        ("板鞋", "休闲低帮板鞋"),
        ("老爹鞋", "复古运动老爹鞋"),
        ("马丁靴", "8孔经典马丁靴"),
        ("豆豆鞋", "舒适软底豆豆鞋"),
        ("凉拖鞋", "EVA 防滑凉拖"),
        ("高跟鞋", "尖头细跟高跟鞋"),
        ("雪地靴", "保暖短筒雪地靴"),
    ],
    "文学小说": [
        ("活着", "余华经典作品"),
        ("百年孤独", "马尔克斯魔幻现实主义"),
        ("三体全集", "刘慈欣科幻巨作"),
        ("红楼梦", "中国古典四大名著"),
        ("平凡的世界", "路遥茅盾文学奖"),
        ("月亮与六便士", "毛姆代表作"),
        ("1984", "乔治·奥威尔反乌托邦"),
        ("围城", "钱钟书经典小说"),
        ("解忧杂货店", "东野圭吾温情作品"),
        ("人类简史", "尤瓦尔·赫拉利畅销书"),
    ],
    "教育考试": [
        ("考研英语词汇", "考研英语红宝书"),
        ("高等数学辅导", "同济大学教材配套"),
        ("Python编程从入门到实践", "零基础编程教程"),
        ("数据结构与算法", "计算机考研教材"),
        ("行测5000题", "公务员考试必备"),
        ("肖秀荣考研政治", "考研政治冲刺"),
        ("雅思词汇真经", "雅思备考词汇书"),
        ("经济学原理", "曼昆经典教材"),
        ("Photoshop从入门到精通", "PS 教程"),
        ("国家地理儿童百科", "少儿科普读物"),
    ],
}


class Command(BaseCommand):
    help = "生成压测所需的测试数据（分类/品牌/规格/商品/用户）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sku-per-spu", type=int, default=5, help="每个 SPU 生成的 SKU 数量"
        )

    def handle(self, *args, **options):
        sku_per_spu = options["sku_per_spu"]
        self._create_specs()
        self._create_categories()
        self._create_brands()
        users = self._create_users()
        self._create_products(sku_per_spu)
        self.stdout.write(self.style.SUCCESS("测试数据生成完毕!"))

    # ── Specs ──────────────────────────────────────────────────────

    def _create_specs(self):
        for group_name, values in SPEC_GROUPS.items():
            parent, _ = BaykeShopSpec.objects.get_or_create(
                name=group_name, parent=None, defaults={"is_show": True}
            )
            for val in values:
                BaykeShopSpec.objects.get_or_create(
                    name=val, parent=parent, defaults={"is_show": True}
                )
        self.stdout.write(f"  [OK] specs ({len(SPEC_GROUPS)} groups)")

    # ── Categories ─────────────────────────────────────────────────

    def _create_categories(self):
        for parent_name, info in CATEGORIES.items():
            parent, _ = BaykeShopCategory.objects.get_or_create(
                name=parent_name,
                parent=None,
                defaults={
                    "is_show": True,
                    "is_floor": True,
                    "is_nav": info["is_nav"],
                    "icon": random.choice(["home", "phone", "tv", "heart", "book"]),
                },
            )
            for child_name in info["children"]:
                BaykeShopCategory.objects.get_or_create(
                    name=child_name,
                    parent=parent,
                    defaults={"is_show": True},
                )
        self.stdout.write(
            f"  [OK] categories ({sum(1 + len(v['children']) for v in CATEGORIES.values())})"
        )

    # ── Brands ─────────────────────────────────────────────────────

    def _create_brands(self):
        image = _make_placeholder_image("brand")
        for name in BRANDS:
            BaykeShopBrand.objects.get_or_create(
                name=name,
                defaults={
                    "description": f"{name}官方旗舰",
                    "image": image,
                },
            )
        self.stdout.write(f"  [OK] brands ({len(BRANDS)})")

    # ── Users ──────────────────────────────────────────────────────

    def _create_users(self):
        users = []
        for i in range(1, 11):
            username = f"testuser{i}"
            user, created = User.objects.get_or_create(
                username=username, defaults={"email": f"{username}@test.com"}
            )
            if created:
                user.set_password("testpass123")
                user.save()
                BaykeShopUser.objects.create(
                    user=user,
                    nickname=f"测试用户{i}",
                    gender=random.choice(["male", "female"]),
                )
            users.append(user)
        self.stdout.write("  [OK] users (10)")
        return users

    # ── Products ───────────────────────────────────────────────────

    def _create_products(self, sku_per_spu):
        brands = list(BaykeShopBrand.objects.all())

        total = 0
        for category_name, products in PRODUCT_TEMPLATES.items():
            try:
                cat = BaykeShopCategory.objects.get(name=category_name, parent__isnull=False)
            except BaykeShopCategory.DoesNotExist:
                self.stdout.write(f"  [WARN] skip category {category_name} (not found)")
                continue

            parent_cat = cat.parent
            # 确定该品类用什么规格组合
            if category_name in ("智能手机",):
                spec_combos = [
                    [{"parent__name": "颜色", "name": c}, {"parent__name": "容量", "name": v}]
                    for c in ("黑色", "白色", "金色")
                    for v in ("128G", "256G", "512G")
                ]
            elif category_name in ("电脑整机", "电脑配件"):
                spec_combos = [
                    [{"parent__name": "版本", "name": v}, {"parent__name": "容量", "name": c}]
                    for v in ("标准版", "尊享版")
                    for c in ("256G", "512G", "1T")
                ]
            elif category_name in ("男装", "女装", "鞋靴"):
                spec_combos = [
                    [{"parent__name": "颜色", "name": c}, {"parent__name": "尺寸", "name": s}]
                    for c in ("黑色", "白色") for s in ("M", "L", "XL")
                ]
            elif category_name in ("图书音像", "文学小说", "教育考试"):
                spec_combos = [
                    [{"parent__name": "版本", "name": "标准版"}],
                    [{"parent__name": "版本", "name": "尊享版"}],
                ]
            else:
                # 办公设备、数码配件、生活电器、厨房电器、个护健康
                spec_combos = [
                    [{"parent__name": "颜色", "name": c}, {"parent__name": "版本", "name": v}]
                    for c in ("黑色", "白色") for v in ("标准版", "尊享版")
                ]

            for name, desc in products:
                with transaction.atomic():
                    goods = BaykeShopGoods.objects.create(
                        name=name,
                        keywords=desc,
                        description=desc,
                        detail=f"<p>{desc}</p><p>精选优质材料，匠心制造。</p>",
                        brand=random.choice(brands),
                        status=BaykeShopGoods.Status.ONLINE,
                        is_recommend=random.random() < 0.15,
                        goods_type=BaykeShopGoods.GoodsType.NORMAL,
                    )
                    goods.category.add(cat, parent_cat)

                    # 创建 SKU
                    selected_combos = random.sample(
                        spec_combos, min(sku_per_spu, len(spec_combos))
                    )
                    for combo in selected_combos:
                        base_price = random.randint(9900, 999900) / 100
                        BaykeShopGoodsSKU.objects.create(
                            goods=goods,
                            specs=combo,
                            price=base_price,
                            line_price=round(base_price * random.uniform(1.1, 1.4), 2),
                            stock=random.randint(10, 999),
                            sales=random.randint(0, 5000),
                            sku_sn=f"SN{goods.id:04d}{random.randint(100,999)}",
                        )

                    # 创建商品图片
                    img_content = _make_placeholder_image(goods.name[:20])
                    BaykeShopGoodsImages.objects.create(
                        goods=goods,
                        image=img_content,
                        order=1,
                    )

                total += 1
                if total % 20 == 0:
                    self.stdout.write(f"  ... created {total} SPU")

        self.stdout.write(f"  [OK] goods ({total} SPU, {total * sku_per_spu} SKU)")
