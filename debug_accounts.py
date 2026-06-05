import asyncio
from sqlalchemy import select
from apps.api.app.db.session import AsyncSessionLocal
from apps.api.app.models import BrokerAccount

async def check():
    async with AsyncSessionLocal() as db:
        accounts = await db.scalars(select(BrokerAccount).where(BrokerAccount.account_type == 'MASTER'))
        accounts_list = list(accounts)
        if not accounts_list:
            print("No master accounts found")
            return
        for account in accounts_list:
            print(f"Account: {account.account_name} ({account.id})")
            print(f"  API Key: {'YES' if account.api_key else 'NO'}")
            print(f"  Access Token: {'YES' if account.access_token else 'NO'}")
            print(f"  Customer ID: {'YES' if account.customer_id else 'NO'}")
            print(f"  Login ID: {'YES' if account.login_id else 'NO'}")
            print()

asyncio.run(check())
