"""Locust load test for BaykeShop.

Scenarios:
  A: Home + List browsing (read-heavy)
  B: Product detail (read-heavy + PV/UV)
  C: Login + Cart (read-write mix)
"""

import re
import random
from locust import HttpUser, task, between

SPU_IDS = list(range(324, 484))
SKU_IDS = list(range(1143, 1833))
CATEGORY_IDS = [2, 4, 5, 6, 8, 9, 11, 12, 13, 15, 16, 17, 19, 20]
USERS = [
    {"username": f"testuser{i}", "password": "testpass123"}
    for i in range(1, 11)
]
SEARCH_KW = ["手机", "电脑", "小米", "华为", "图书"]


class BaykeShopUser(HttpUser):
    wait_time = between(0.5, 3)

    def _login(self, user):
        resp = self.client.get("/member/login/")
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', resp.text)
        if m:
            self.client.post(
                "/member/login/",
                {"csrfmiddlewaretoken": m.group(1), "username": user["username"], "password": user["password"]},
            )

    def _get_csrf_token(self):
        return self.client.cookies.get("csrftoken", "")

    # ── Scenario A: Home + List browsing ──────────────────────

    @task(3)
    def browse_home(self):
        self.client.get("/", name="A: homepage")

    @task(2)
    def browse_list(self):
        self.client.get("/list/", name="A: list")

    @task(1)
    def browse_list_page2(self):
        self.client.get("/list/?page=2", name="A: list page2")

    @task(2)
    def browse_category(self):
        self.client.get(f"/category/{random.choice(CATEGORY_IDS)}/", name="A: category")

    @task(1)
    def search(self):
        self.client.get(f"/search/?keyword={random.choice(SEARCH_KW)}", name="A: search")

    # ── Scenario B: Product detail ────────────────────────────

    @task(3)
    def view_detail(self):
        self.client.get(f"/detail/{random.choice(SPU_IDS)}/", name="B: detail")

    # ── Scenario C: Login + Cart ──────────────────────────────

    @task(1)
    def login_and_cart(self):
        user = random.choice(USERS)
        self._login(user)
        csrf = self._get_csrf_token()
        self.client.get("/carts/", name="C: cart list")
        self.client.post(
            "/api/carts/",
            {"sku": random.choice(SKU_IDS), "quantity": 1},
            headers={"X-CSRFToken": csrf},
            name="C: add to cart",
        )
