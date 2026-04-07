# Trading Journal Backend

Django REST API for the Trading Journal application.

## Features

- User authentication with JWT tokens
- Trade management (CRUD operations)
- MT5 integration (manual import + connection)
- Analytics and reporting
- Journal entries and goals
- Market data and news
- PostgreSQL database

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create PostgreSQL Database

```bash
createdb trading_journal
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Run Development Server

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/`

## API Endpoints

### Authentication
- `POST /api/auth/register/` - Register new user
- `POST /api/auth/login/` - Login
- `POST /api/auth/logout/` - Logout
- `POST /api/auth/refresh/` - Refresh token
- `GET /api/auth/profile/` - Get user profile
- `PUT /api/auth/profile/` - Update user profile
- `POST /api/auth/change-password/` - Change password

### Trades
- `GET /api/trades/` - List trades
- `POST /api/trades/` - Create trade
- `GET /api/trades/<id>/` - Get trade details
- `PUT /api/trades/<id>/` - Update trade
- `DELETE /api/trades/<id>/` - Delete trade
- `POST /api/trades/bulk-delete/` - Bulk delete trades
- `GET /api/trades/statistics/` - Trade statistics
- `GET /api/trades/analytics/` - Trade analytics
- `GET /api/trades/dashboard/summary/` - Dashboard summary

### MT5 Integration
- `GET /api/mt5/accounts/` - List MT5 accounts
- `POST /api/mt5/accounts/` - Add MT5 account
- `POST /api/mt5/test-connection/` - Test MT5 connection
- `POST /api/mt5/sync/` - Sync trades from MT5
- `GET /api/mt5/imports/` - Import history
- `GET /api/mt5/setup-guide/` - Setup guide
- `GET /api/mt5/manual-import-guide/` - Manual import guide

### Analytics
- `GET /api/analytics/reports/` - Performance reports
- `POST /api/analytics/reports/generate/` - Generate report
- `GET /api/analytics/equity-curve/` - Equity curve data
- `GET /api/analytics/drawdown/` - Drawdown analysis
- `GET /api/analytics/insights/` - Trading insights
- `GET /api/analytics/calendar-heatmap/` - Calendar heatmap

### Journal
- `GET /api/journal/entries/` - Journal entries
- `POST /api/journal/entries/` - Create entry
- `GET /api/journal/goals/` - Trading goals
- `POST /api/journal/goals/` - Create goal
- `GET /api/journal/plans/` - Trading plans
- `GET /api/journal/summary/` - Journal summary

### Market Data
- `GET /api/market/news/` - Market news
- `GET /api/market/calendar/` - Economic calendar
- `GET /api/market/prices/` - Market prices
- `GET /api/market/instruments/` - Trading instruments
- `GET /api/market/overview/` - Market overview

## MT5 Integration

Since Python 3.14 doesn't support the MT5 API directly, we provide two methods:

### Method 1: Manual Import
1. Export trades from MT5 as HTML or CSV
2. Upload through the web interface
3. Trades are automatically parsed and imported

### Method 2: EA (Expert Advisor)
1. Install the provided EA in MT5
2. Configure the EA with your API credentials
3. Trades sync automatically in real-time

See the setup guide at `/api/mt5/setup-guide/` for detailed instructions.
