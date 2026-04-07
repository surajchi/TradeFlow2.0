# Trading Journal Application

A comprehensive trading journal application built with Django REST API and React. Track your trades, analyze performance, and improve your trading results.

## Features

### Core Features
- **Trade Management**: Add, edit, delete, and track all your trades
- **Dashboard**: Overview of your trading performance with key metrics
- **Analytics**: Deep insights into your trading patterns and performance
- **Journal**: Document your trades, set goals, and track your progress
- **Market Data**: Stay updated with market news and economic calendar
- **MT5 Integration**: Connect your MetaTrader 5 account for automatic trade syncing

### Key Capabilities
- **Dark/Light Mode**: Full theme support with smooth transitions
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Real-time Charts**: Visualize your equity curve and performance metrics
- **Trade Analytics**: Win rate, profit factor, drawdown analysis, and more
- **Emotion Tracking**: Log your emotions to understand psychological patterns
- **Strategy Management**: Track performance by strategy
- **Goal Setting**: Set and track trading goals

## Tech Stack

### Backend
- **Django 5.0+**: Python web framework
- **Django REST Framework**: API development
- **PostgreSQL**: Database
- **JWT Authentication**: Secure user authentication
- **Celery + Redis**: Background tasks (optional)

### Frontend
- **React 18**: UI library
- **Vite**: Build tool
- **Tailwind CSS**: Styling
- **shadcn/ui**: UI components
- **Recharts**: Charts and visualizations
- **Framer Motion**: Animations

## Project Structure

```
trading-journal/
├── backend/                 # Django backend
│   ├── accounts/           # User authentication
│   ├── trades/             # Trade management
│   ├── analytics/          # Analytics and reporting
│   ├── journal/            # Journal entries and goals
│   ├── market_data/        # Market news and prices
│   ├── mt5_integration/    # MT5 integration
│   └── trading_journal/    # Django settings
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── contexts/      # React contexts
│   │   ├── pages/         # Page components
│   │   ├── services/      # API services
│   │   └── utils/         # Utilities
│   └── public/
└── README.md
```

## Setup Instructions

### Prerequisites
- Python 3.14+
- Node.js 18+
- PostgreSQL 14+
- Redis (optional, for Celery)

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a PostgreSQL database:
```bash
createdb trading_journal
```

5. Copy the environment file and configure:
```bash
cp .env.example .env
# Edit .env with your database credentials
```

6. Run migrations:
```bash
python manage.py migrate
```

7. Create a superuser:
```bash
python manage.py createsuperuser
```

8. Run the development server:
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file:
```bash
VITE_API_URL=http://localhost:8000/api
```

4. Run the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173/`

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

See the MT5 Setup Guide in the application for detailed instructions.

## API Endpoints

### Authentication
- `POST /api/auth/register/` - Register new user
- `POST /api/auth/login/` - Login
- `POST /api/auth/logout/` - Logout
- `GET /api/auth/profile/` - Get user profile

### Trades
- `GET /api/trades/` - List trades
- `POST /api/trades/` - Create trade
- `GET /api/trades/<id>/` - Get trade details
- `PUT /api/trades/<id>/` - Update trade
- `DELETE /api/trades/<id>/` - Delete trade
- `GET /api/trades/statistics/` - Trade statistics
- `GET /api/trades/analytics/` - Trade analytics

### MT5
- `GET /api/mt5/accounts/` - List MT5 accounts
- `POST /api/mt5/accounts/` - Add MT5 account
- `POST /api/mt5/sync/` - Sync trades from MT5
- `GET /api/mt5/setup-guide/` - Setup guide

## Environment Variables

### Backend (.env)
```
SECRET_KEY=your-secret-key
DEBUG=True
DB_NAME=trading_journal
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
REDIS_URL=redis://localhost:6379/0
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000/api
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support, please open an issue on GitHub or contact us at support@tradejournal.com
