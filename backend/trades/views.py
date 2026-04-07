from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Avg, Count, Q, Max, Min, F
from django.db.models.functions import ExtractWeekDay, ExtractHour, TruncMonth
from django.utils import timezone
from datetime import timedelta
import pandas as pd

from .models import Trade, TradeImport, Strategy
from .serializers import (
    TradeSerializer, TradeCreateSerializer, TradeUpdateSerializer,
    TradeListSerializer, TradeImportSerializer, StrategySerializer,
    TradeStatisticsSerializer
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class TradeListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['symbol', 'trade_type', 'status', 'market_type', 'strategy']
    ordering_fields = ['entry_date', 'exit_date', 'profit_loss', 'created_at']
    search_fields = ['symbol', 'strategy', 'notes', 'tags']
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TradeCreateSerializer
        return TradeListSerializer
    
    def get_queryset(self):
        queryset = Trade.objects.filter(user=self.request.user)
        
        # Date range filtering
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(entry_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(entry_date__lte=date_to)
        
        # Profit/Loss filtering
        profit_min = self.request.query_params.get('profit_min')
        profit_max = self.request.query_params.get('profit_max')
        
        if profit_min:
            queryset = queryset.filter(profit_loss__gte=profit_min)
        if profit_max:
            queryset = queryset.filter(profit_loss__lte=profit_max)
        
        # Tags filtering
        tags = self.request.query_params.get('tags')
        if tags:
            tag_list = tags.split(',')
            for tag in tag_list:
                queryset = queryset.filter(tags__contains=[tag.strip()])
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradeSerializer
    
    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return TradeUpdateSerializer
        return TradeSerializer
    
    def perform_update(self, serializer):
        instance = serializer.save()
        # Recalculate P&L if trade is closed
        if instance.status == 'CLOSED' and instance.exit_price:
            instance.calculate_profit_loss()
            instance.save()


class TradeBulkDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        trade_ids = request.data.get('trade_ids', [])
        if not trade_ids:
            return Response(
                {'error': 'No trade IDs provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        deleted_count = Trade.objects.filter(
            user=request.user,
            id__in=trade_ids
        ).delete()[0]
        
        return Response({
            'message': f'{deleted_count} trades deleted successfully.'
        })


class TradeStatisticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Get date range from query params
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        trades = Trade.objects.filter(user=user, status='CLOSED')
        
        if date_from:
            trades = trades.filter(entry_date__gte=date_from)
        if date_to:
            trades = trades.filter(entry_date__lte=date_to)
        
        # Basic statistics
        total_trades = trades.count()
        
        if total_trades == 0:
            return Response({
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_profit': 0.0,
                'total_loss': 0.0,
                'net_pnl': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_trade': 0.0,
                'largest_profit': 0.0,
                'largest_loss': 0.0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0,
                'avg_holding_time': '0h 0m',
                'total_commission': 0.0,
                'total_swap': 0.0,
            })
        
        winning_trades = trades.filter(profit_loss__gt=0)
        losing_trades = trades.filter(profit_loss__lte=0)
        
        # Calculate statistics (Defaulting to 0 to prevent NoneType errors)
        total_profit = float(winning_trades.aggregate(Sum('profit_loss'))['profit_loss__sum'] or 0)
        total_loss = abs(float(losing_trades.aggregate(Sum('profit_loss'))['profit_loss__sum'] or 0))
        
        win_count = winning_trades.count()
        loss_count = losing_trades.count()
        
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
        
        avg_profit = float(winning_trades.aggregate(Avg('profit_loss'))['profit_loss__avg'] or 0)
        avg_loss = abs(float(losing_trades.aggregate(Avg('profit_loss'))['profit_loss__avg'] or 0))
        
        # FIX: Safe Profit Factor calculation (Prevents JSON 'inf' error)
        if total_loss > 0:
            profit_factor = total_profit / total_loss
        else:
            profit_factor = 0.0  # Fallback when there are no losses
        
        net_pnl = total_profit - total_loss
        avg_trade = net_pnl / total_trades if total_trades > 0 else 0.0
        
        largest_profit = float(winning_trades.aggregate(Max('profit_loss'))['profit_loss__max'] or 0)
        largest_loss = float(losing_trades.aggregate(Min('profit_loss'))['profit_loss__min'] or 0)
        
        # Commission and swap
        total_commission = float(trades.aggregate(Sum('commission'))['commission__sum'] or 0)
        total_swap = float(trades.aggregate(Sum('swap'))['swap__sum'] or 0)
        
        # Average holding time
        holding_times = []
        for trade in trades:
            if trade.exit_date and trade.entry_date:
                holding_times.append((trade.exit_date - trade.entry_date).total_seconds())
        
        avg_holding_seconds = sum(holding_times) / len(holding_times) if holding_times else 0
        avg_hours = int(avg_holding_seconds // 3600)
        avg_minutes = int((avg_holding_seconds % 3600) // 60)
        avg_holding_time = f"{avg_hours}h {avg_minutes}m"
        
        # Consecutive wins/losses
        trades_ordered = trades.order_by('entry_date')
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        
        for trade in trades_ordered:
            if trade.profit_loss and trade.profit_loss > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)
        
        data = {
            'total_trades': total_trades,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': round(win_rate, 2),
            'total_profit': round(total_profit, 2),
            'total_loss': round(total_loss, 2),
            'net_pnl': round(net_pnl, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'avg_trade': round(avg_trade, 2),
            'largest_profit': round(largest_profit, 2),
            'largest_loss': round(largest_loss, 2),
            'max_consecutive_wins': max_consecutive_wins,
            'max_consecutive_losses': max_consecutive_losses,
            'avg_holding_time': avg_holding_time,
            'total_commission': round(total_commission, 2),
            'total_swap': round(total_swap, 2),
        }
        
        return Response(data)


class TradeAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Get date range
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        trades = Trade.objects.filter(user=user, status='CLOSED')
        
        if date_from:
            trades = trades.filter(entry_date__gte=date_from)
        if date_to:
            trades = trades.filter(entry_date__lte=date_to)
        
        # Analytics by symbol
        symbol_stats = list(trades.values('symbol').annotate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(profit_loss__gt=0)),
            total_pnl=Sum('profit_loss'),
            avg_pnl=Avg('profit_loss')
        ).order_by('-total_pnl'))
        
        # Analytics by strategy
        strategy_stats = list(trades.values('strategy').annotate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(profit_loss__gt=0)),
            total_pnl=Sum('profit_loss'),
            avg_pnl=Avg('profit_loss')
        ).order_by('-total_pnl'))
        
        # FIX: Database Agnostic queries (Works on SQLite, Postgres, MySQL)
        
        # Analytics by day of week (1=Sunday, 7=Saturday)
        day_stats_raw = trades.annotate(
            day_num=ExtractWeekDay('entry_date')
        ).values('day_num').annotate(
            total_trades=Count('id'),
            total_pnl=Sum('profit_loss'),
            avg_pnl=Avg('profit_loss')
        ).order_by('day_num')
        
        days_map = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday', 5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
        day_stats = []
        for stat in day_stats_raw:
            stat['day_of_week'] = days_map.get(stat.pop('day_num'), 'Unknown')
            day_stats.append(stat)
        
        # Analytics by hour
        hour_stats = list(trades.annotate(
            hour=ExtractHour('entry_date')
        ).values('hour').annotate(
            total_trades=Count('id'),
            total_pnl=Sum('profit_loss'),
            avg_pnl=Avg('profit_loss')
        ).order_by('hour'))
        
        # Monthly performance
        monthly_stats_raw = trades.annotate(
            month_date=TruncMonth('entry_date')
        ).values('month_date').annotate(
            total_trades=Count('id'),
            winning_trades=Count('id', filter=Q(profit_loss__gt=0)),
            total_pnl=Sum('profit_loss'),
            avg_pnl=Avg('profit_loss')
        ).order_by('month_date')
        
        monthly_stats = []
        for stat in monthly_stats_raw:
            m_date = stat.pop('month_date')
            if m_date:
                stat['month'] = m_date.strftime('%Y-%m')
                stat['month_name'] = m_date.strftime('%B %Y')
                monthly_stats.append(stat)
        
        return Response({
            'symbol_performance': symbol_stats,
            'strategy_performance': strategy_stats,
            'day_of_week_performance': day_stats,
            'hour_performance': hour_stats,
            'monthly_performance': monthly_stats,
        })


class TradeImportView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradeImportSerializer
    
    def get_queryset(self):
        return TradeImport.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StrategyListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StrategySerializer
    
    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class StrategyDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StrategySerializer
    
    def get_queryset(self):
        return Strategy.objects.filter(user=self.request.user)


class DashboardSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        today = timezone.now().date()
        
        # Today's trades
        today_trades = Trade.objects.filter(
            user=user,
            entry_date__date=today
        )
        
        # This week's trades
        week_start = today - timedelta(days=today.weekday())
        week_trades = Trade.objects.filter(
            user=user,
            entry_date__date__gte=week_start
        )
        
        # This month's trades
        month_start = today.replace(day=1)
        month_trades = Trade.objects.filter(
            user=user,
            entry_date__date__gte=month_start
        )
        
        # All closed trades
        all_trades = Trade.objects.filter(user=user, status='CLOSED')
        
        # Calculate summaries safely
        def get_summary(trades):
            closed = trades.filter(status='CLOSED')
            return {
                'total_trades': trades.count(),
                'closed_trades': closed.count(),
                'open_trades': trades.filter(status='OPEN').count(),
                'pnl': float(closed.aggregate(Sum('profit_loss'))['profit_loss__sum'] or 0),
                'winning_trades': closed.filter(profit_loss__gt=0).count(),
                'losing_trades': closed.filter(profit_loss__lte=0).count(),
            }
        
        return Response({
            'today': get_summary(today_trades),
            'this_week': get_summary(week_trades),
            'this_month': get_summary(month_trades),
            'all_time': get_summary(all_trades),
            'recent_trades': TradeListSerializer(
                all_trades.order_by('-entry_date')[:5],
                many=True
            ).data
        })