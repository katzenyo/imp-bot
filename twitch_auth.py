import logging
import os
import time
import aiohttp
import aiosqlite
from dotenv import load_dotenv

log = logging.getLogger(__name__)
load_dotenv(override=True)

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
DB_PATH = "impbot.db"
_REFRESH_BUFFER = 3600  # refresh when less than 1 hour remains


async def ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute('''
        CREATE TABLE IF NOT EXISTS twitch_tokens (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    ''')
    await db.commit()


async def seed_from_env(db: aiosqlite.Connection) -> None:
    """Seeds the DB with tokens from .env on first run. No-op if already seeded."""
    async with db.execute('SELECT id FROM twitch_tokens WHERE id = 1') as cursor:
        if await cursor.fetchone():
            return

    access_token = os.getenv('TWITCH_ACCESS_TOKEN')
    refresh_token = os.getenv('TWITCH_REFRESH_TOKEN')
    if not access_token or not refresh_token:
        log.warning('[TWITCH_AUTH] TWITCH_ACCESS_TOKEN or TWITCH_REFRESH_TOKEN missing from .env — cannot seed tokens')
        print('[TWITCH_AUTH] Set TWITCH_ACCESS_TOKEN and TWITCH_REFRESH_TOKEN in .env to enable Twitch features.')
        return

    expires_at = await _fetch_expiry(access_token)
    await db.execute(
        'INSERT INTO twitch_tokens (id, access_token, refresh_token, expires_at) VALUES (1, ?, ?, ?)',
        (access_token, refresh_token, expires_at)
    )
    await db.commit()
    log.info('[TWITCH_AUTH] Seeded Twitch tokens from .env')
    print('[TWITCH_AUTH] Seeded Twitch tokens from .env into database.')


async def log_status(db: aiosqlite.Connection) -> None:
    """Logs the current token expiry status."""
    async with db.execute('SELECT expires_at FROM twitch_tokens WHERE id = 1') as cursor:
        row = await cursor.fetchone()
    if not row:
        log.warning('[TWITCH_AUTH] No tokens in database')
        return

    remaining = row[0] - int(time.time())
    if remaining <= 0:
        log.warning('[TWITCH_AUTH] Token has expired — will attempt refresh on next use')
        print('[TWITCH_AUTH] Token has expired — will refresh automatically.')
    elif remaining < 3600 * 24 * 7:
        hours = remaining // 3600
        log.warning('[TWITCH_AUTH] Token expires in %d hours — will auto-refresh', hours)
        print(f'[TWITCH_AUTH] Token expires in {hours} hours (auto-refresh enabled).')
    else:
        days = remaining // 86400
        log.info('[TWITCH_AUTH] Token valid for %d more days', days)
        print(f'[TWITCH_AUTH] Token valid for {days} more days.')


async def get_access_token(db: aiosqlite.Connection) -> str:
    """Returns a valid access token, refreshing automatically if near expiry."""
    async with db.execute(
        'SELECT access_token, refresh_token, expires_at FROM twitch_tokens WHERE id = 1'
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        raise RuntimeError(
            'No Twitch tokens in database. Set TWITCH_ACCESS_TOKEN and TWITCH_REFRESH_TOKEN in .env and restart.'
        )

    if int(time.time()) >= row[2] - _REFRESH_BUFFER:
        return await _do_refresh(db, row[1])

    return row[0]


async def get_headers(db: aiosqlite.Connection) -> dict:
    """Returns Twitch API headers with a valid access token."""
    token = await get_access_token(db)
    return {
        'Authorization': f'Bearer {token}',
        'Client-Id': TWITCH_CLIENT_ID or '',
    }


async def force_refresh(db: aiosqlite.Connection) -> str:
    """Forces a token refresh regardless of expiry. Returns the new access token."""
    async with db.execute('SELECT refresh_token FROM twitch_tokens WHERE id = 1') as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError('No Twitch tokens in database.')
    return await _do_refresh(db, row[0])


async def _fetch_expiry(access_token: str) -> int:
    """Validates a token with Twitch and returns its Unix expiry timestamp."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            'https://id.twitch.tv/oauth2/validate',
            headers={'Authorization': f'Bearer {access_token}'}
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return int(time.time()) + data['expires_in']
    # Token invalid or expired — return 0 so it refreshes immediately on first use
    return 0


async def _do_refresh(db: aiosqlite.Connection, refresh_token: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'https://id.twitch.tv/oauth2/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': TWITCH_CLIENT_ID,
                'client_secret': TWITCH_CLIENT_SECRET,
            }
        ) as resp:
            body = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f'Token refresh failed ({resp.status}): {body}')

    expires_at = int(time.time()) + body['expires_in']
    await db.execute(
        'UPDATE twitch_tokens SET access_token = ?, refresh_token = ?, expires_at = ? WHERE id = 1',
        (body['access_token'], body['refresh_token'], expires_at)
    )
    await db.commit()
    log.info('[TWITCH_AUTH] Token refreshed successfully')
    print('[TWITCH_AUTH] Token refreshed successfully.')
    return body['access_token']
