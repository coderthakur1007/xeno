import argparse
import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import create_engine, text

from app.core.config import get_settings

fake = Faker("en_IN")
random.seed(42)

BRANDS = ["Aster Apparel", "GlowCart", "Urban Pantry", "Nira Beauty", "Stride Studio"]
CITIES = ["Mumbai", "Delhi", "Bangalore", "Pune", "Hyderabad", "Chennai", "Ahmedabad", "Kolkata"]
CHANNELS = ["whatsapp", "sms", "email", "rcs"]
CATEGORIES = ["skincare", "apparel", "grocery", "footwear", "wellness", "home"]
EVENTS = ["delivered", "opened", "read", "clicked", "converted", "failed"]

CAMPAIGNS_SEED = [
    {
        "name": "Seeded reactivation campaign",
        "goal": "Increase repeat purchases from inactive customers",
        "status": "completed",
        "channels": '["whatsapp","email"]',
        "launched_offset_days": 14,
    },
    {
        "name": "VIP winback campaign",
        "goal": "Win back VIP customers who viewed products but did not buy this month",
        "status": "running",
        "channels": '["whatsapp","sms","email"]',
        "launched_offset_days": 3,
    },
    {
        "name": "New customer nurture draft",
        "goal": "Convert new shoppers into second-purchase customers",
        "status": "draft",
        "channels": '["email","rcs"]',
        "launched_offset_days": None,
    },
]

TRANSACTION_TYPES = ["payment", "refund", "chargeback"]
TRANSACTION_STATUSES = ["completed", "pending", "failed"]


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _hash_password(password: str) -> str:
    """SHA-256 hash with xeno_salt_ prefix — matches the demo convention."""
    salted = f"xeno_salt_{password}"
    return hashlib.sha256(salted.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=int, default=25000)
    parser.add_argument("--orders", type=int, default=90000)
    parser.add_argument("--events", type=int, default=160000)
    parser.add_argument("--demo-user", action="store_true", help="Create demo login user (demo@xeno.ai / demo1234)")
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenants(name, plan) VALUES (:name, 'enterprise')"),
            {"name": random.choice(BRANDS)},
        )
        tenant_id = conn.execute(text("SELECT id FROM tenants ORDER BY created_at DESC LIMIT 1")).scalar_one()
        conn.execute(
            text(
                "INSERT INTO users(tenant_id, email, full_name, role) VALUES "
                "(:tenant_id, 'admin@xeno.local', 'Demo Admin', 'admin') "
            ),
            {"tenant_id": tenant_id},
        )
        user_id = conn.execute(text("SELECT id FROM users ORDER BY created_at DESC LIMIT 1")).scalar_one()

        # ---- Demo user with known credentials ----
        if args.demo_user:
            demo_password_hash = _hash_password("demo1234")
            conn.execute(
            conn.execute(
                text(
                    "INSERT INTO users(tenant_id, email, password_hash, full_name, role) VALUES "
                    "(:tenant_id, 'demo@xeno.ai', :password_hash, 'Demo User', 'admin') "
                ),
                {"tenant_id": tenant_id, "password_hash": demo_password_hash},
            )
            print(f"  Demo user created: email=demo@xeno.ai password=demo1234")

        # ---- Admin settings ----
        settings = [
            ("frequency_caps", {"max_per_customer_per_week": 3, "quiet_hours": ["21:00", "09:00"]}),
            ("attribution", {"model": "last_touch", "window_days": 7}),
            ("channel_budget", {"whatsapp": 0.42, "sms": 0.16, "email": 0.24, "rcs": 0.18}),
        ]
        for key, value in settings:
            conn.execute(text("INSERT INTO admin_settings(tenant_id,key,value) VALUES (:tenant_id,:key,:value) "), {"tenant_id": tenant_id, "key": key, "value": json(value)})
        for key in ["ai_autonomous_execution", "rcs_experiments", "churn_predictions"]:
            conn.execute(text("INSERT INTO feature_flags(tenant_id,key,enabled,config) VALUES (:tenant_id,:key,true,'{}') "), {"tenant_id": tenant_id, "key": key})
        conn.execute(
            text(
                "INSERT INTO prompt_templates(tenant_id,name,version,template,variables) VALUES "
                "(:tenant_id,'campaign_content',1,:template,'[\"goal\",\"channel\",\"customer\"]') "
            ),
            {"tenant_id": tenant_id, "template": "Create a channel-native message for {{goal}} using {{customer}} context."},
        )
        conn.execute(
            text(
                "INSERT INTO model_registry(tenant_id,model_name,version,status,metrics,feature_set,artifact_uri) "
                "VALUES (:tenant_id,'conversion_propensity','2026.06.1','active',:metrics,:features,'s3://xeno-models/conversion/2026.06.1')"
            ),
            {"tenant_id": tenant_id, "metrics": json({"auc": 0.81, "calibration_error": 0.037}), "features": json(["rfm", "channel_affinity", "category_affinity", "discount_sensitivity"])},
        )

        # ---- Customers ----
        customers = []
        for index in range(args.customers):
            customers.append(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "external_id": f"CUST-{index:07d}",
                    "email": fake.email(),
                    "phone": fake.phone_number()[:32],
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                    "city": random.choice(CITIES),
                    "state": fake.state(),
                    "country": "India",
                    "gender": random.choice(["female", "male", "non_binary", None]),
                    "consent": json({"whatsapp": True, "sms": random.random() > 0.08, "email": random.random() > 0.04, "rcs": random.random() > 0.25}),
                    "attributes": json({"preferred_category": random.choice(CATEGORIES), "loyalty_tier": random.choice(["bronze", "silver", "gold", "platinum"])}),
                }
            )
        for batch in chunked(customers, 2000):
            conn.execute(
                text(
                    """
                    INSERT INTO customers(id,tenant_id,external_id,email,phone,first_name,last_name,city,state,country,gender,consent,attributes)
                    VALUES (:id,:tenant_id,:external_id,:email,:phone,:first_name,:last_name,:city,:state,:country,:gender,:consent,:attributes)
                    """
                ),
                batch,
            )

        # ---- Orders ----
        orders = []
        for index in range(args.orders):
            customer = random.choice(customers)
            category = random.choice(CATEGORIES)
            days = int(random.expovariate(1 / 95))
            amount = round(max(199, random.lognormvariate(7.1, 0.75)), 2)
            orders.append(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "customer_id": customer["id"],
                    "external_id": f"ORD-{index:08d}",
                    "status": random.choices(["paid", "refunded", "cancelled"], [0.88, 0.05, 0.07])[0],
                    "total_amount": amount,
                    "channel": random.choice(["online", "store", "marketplace", "app"]),
                    "items": json([{"sku": f"SKU-{random.randint(1000,9999)}", "category": category, "qty": random.randint(1, 4), "price": amount}]),
                    "ordered_at": datetime.now(timezone.utc) - timedelta(days=days, hours=random.randint(0, 23)),
                }
            )
        for batch in chunked(orders, 2000):
            conn.execute(
                text(
                    """
                    INSERT INTO orders(id,tenant_id,customer_id,external_id,status,total_amount,channel,items,ordered_at)
                    VALUES (:id,:tenant_id,:customer_id,:external_id,:status,:total_amount,:channel,:items,:ordered_at)
                    """
                ),
                batch,
            )

        # ---- Transactions for each order ----
        transactions = []
        for order in orders:
            tx_type = "payment"
            tx_status = "completed"
            if order["status"] == "refunded":
                tx_type = random.choice(["refund", "chargeback"])
                tx_status = "completed"
            elif order["status"] == "cancelled":
                tx_type = "payment"
                tx_status = "failed"
            transactions.append(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "order_id": order["id"],
                    "amount": order["total_amount"],
                    "type": tx_type,
                    "status": tx_status,
                }
            )
        for batch in chunked(transactions, 2000):
            conn.execute(
                text(
                    """
                    INSERT INTO transactions(id,tenant_id,order_id,amount,type,status)
                    VALUES (:id,:tenant_id,:order_id,:amount,:type,:status)
                    """
                ),
                batch,
            )

        # ---- 3 Campaigns (completed, running, draft) ----
        campaign_ids = []
        for camp in CAMPAIGNS_SEED:
            launched_clause = "now() - interval '{} days'".format(camp["launched_offset_days"]) if camp["launched_offset_days"] else "NULL"
            conn.execute(
                text(
                    f"INSERT INTO campaigns(tenant_id,name,goal,status,channels,strategy,variants,created_by,launched_at) "
                    f"VALUES (:tenant_id,:name,:goal,:status,'{camp['channels']}',:strategy,:variants,:user_id,{launched_clause}) "
                ),
                {
                    "tenant_id": tenant_id,
                    "name": camp["name"],
                    "goal": camp["goal"],
                    "status": camp["status"],
                    "user_id": user_id,
                    "strategy": json({"conversion_probability": round(random.uniform(0.02, 0.06), 3), "attribution": "7_day_last_touch"}),
                    "variants": json([{"key": "variant_1"}, {"key": "variant_2"}]),
                },
            )
            cid = conn.execute(text("SELECT id FROM campaigns ORDER BY created_at DESC LIMIT 1")).scalar_one()
            campaign_ids.append(cid)
            print(f"  Campaign: {camp['name']} ({camp['status']}) id={cid}")

        # ---- Communication events spread across all campaigns ----
        comms = []
        for index in range(args.events):
            customer = random.choice(customers)
            event_type = random.choices(EVENTS, [0.42, 0.18, 0.17, 0.13, 0.045, 0.055])[0]
            campaign_id = random.choice(campaign_ids)
            channel = random.choice(CHANNELS)
            comms.append(
                {
                    "tenant_id": str(tenant_id),
                    "customer_id": customer["id"],
                    "campaign_id": str(campaign_id),
                    "message_id": None,
                    "channel": channel,
                    "event_type": event_type,
                    "provider_event_id": f"seed_evt_{index}",
                    "metadata": json({"seeded": True, "device": random.choice(["ios", "android", "desktop"]), "channel": channel}),
                    "occurred_at": datetime.now(timezone.utc) - timedelta(days=random.randint(0, 45), minutes=random.randint(0, 1440)),
                }
            )
        for batch in chunked(comms, 3000):
            conn.execute(
                text(
                    """
                    INSERT INTO communication_events(tenant_id,customer_id,campaign_id,message_id,channel,event_type,provider_event_id,metadata,occurred_at)
                    VALUES (:tenant_id,:customer_id,:campaign_id,:message_id,:channel,:event_type,:provider_event_id,:metadata,:occurred_at)
                    """
                ),
                batch,
            )
    print(f"Seeded tenant={tenant_id} customers={args.customers} orders={args.orders} transactions={len(transactions)} events={args.events} campaigns={len(campaign_ids)}")


def json(value) -> str:
    import json as json_module

    return json_module.dumps(value)


if __name__ == "__main__":
    main()
