#!/bin/bash

echo "================================"
echo "Trading Journal Setup"
echo "================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3.14 or higher."
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Node.js is not installed. Please install Node.js 18 or higher."
    exit 1
fi

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL is not installed. Please install PostgreSQL 14 or higher."
    exit 1
fi

echo "All prerequisites are installed!"
echo ""

# Setup Backend
echo "Setting up Backend..."
cd backend

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Create database
echo "Creating PostgreSQL database..."
psql -U postgres -c "CREATE DATABASE trading_journal;" 2>/dev/null || echo "Database may already exist"

# Copy environment file
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "Please edit .env file with your database credentials"
fi

# Run migrations
echo "Running migrations..."
python manage.py migrate

echo ""
echo "Backend setup complete!"
echo ""

# Setup Frontend
echo "Setting up Frontend..."
cd ../frontend

# Install dependencies
echo "Installing Node.js dependencies..."
npm install

# Create environment file
if [ ! -f .env ]; then
    echo "Creating .env file..."
    echo "VITE_API_URL=http://localhost:8000/api" > .env
fi

echo ""
echo "Frontend setup complete!"
echo ""

# Instructions
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "To start the application:"
echo ""
echo "1. Start the backend server:"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo ""
echo "2. In a new terminal, start the frontend:"
echo "   cd frontend"
echo "   npm run dev"
echo ""
echo "3. Open http://localhost:5173 in your browser"
echo ""
echo "Default admin credentials:"
echo "   Email: admin@example.com"
echo "   Password: (create using: python manage.py createsuperuser)"
echo ""
