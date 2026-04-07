from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from .models import PerformanceReport, TradingInsight
from trades.models import Trade
from .serializers import (
    PerformanceReportSerializer, TradingInsightSerializer,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _base_trades(user, date_from=None, date_to=None):
    """Return a closed-trade queryset filtered by optional date range."""
    qs = Trade.objects.filter(user=user, status="CLOSED").order_by("entry_date")
    if date_from:
        qs = qs.filter(entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry_date__lte=date_to)
    return qs


# ─── Performance Reports ───────────────────────────────────────────────────────

class PerformanceReportListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = PerformanceReportSerializer

    def get_queryset(self):
        return PerformanceReport.objects.filter(user=self.request.user)


class GenerateReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        report_type = request.data.get("report_type", "MONTHLY")
        date_from   = request.data.get("date_from")
        date_to     = request.data.get("date_to")
        user        = request.user

        trades = _base_trades(user, date_from, date_to)

        if not trades.exists():
            return Response(
                {"error": "No trades found for the specified period."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_trades    = trades.count()
        winning_trades  = trades.filter(profit_loss__gt=0)
        losing_trades   = trades.filter(profit_loss__lte=0)
        win_count       = winning_trades.count()
        loss_count      = losing_trades.count()
        win_rate        = (win_count / total_trades * 100) if total_trades else 0

        gross_profit = float(winning_trades.aggregate(Sum("profit_loss"))["profit_loss__sum"] or 0)
        gross_loss   = abs(float(losing_trades.aggregate(Sum("profit_loss"))["profit_loss__sum"] or 0))
        net_profit   = gross_profit - gross_loss
        profit_factor= (gross_profit / gross_loss) if gross_loss else 999.99

        # Average trade / win / loss
        avg_trade = float(trades.aggregate(Avg("profit_loss"))["profit_loss__avg"] or 0)
        avg_win   = float(winning_trades.aggregate(Avg("profit_loss"))["profit_loss__avg"] or 0)
        avg_loss  = float(losing_trades.aggregate(Avg("profit_loss"))["profit_loss__avg"] or 0)

        # Max drawdown (sequential pass)
        pnls       = [float(t.profit_loss or 0) for t in trades]
        cumulative = peak = max_dd = max_dd_amt = 0.0
        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            dd_pct = (dd / peak * 100) if peak > 0 else 0
            if dd > max_dd_amt:
                max_dd_amt = dd
                max_dd     = dd_pct

        # Consecutive wins / losses
        max_cw = max_cl = cur_w = cur_l = 0
        for pnl in pnls:
            if pnl > 0:
                cur_w += 1; cur_l = 0
            else:
                cur_l += 1; cur_w = 0
            max_cw = max(max_cw, cur_w)
            max_cl = max(max_cl, cur_l)

        report = PerformanceReport.objects.create(
            user                  = user,
            report_type           = report_type,
            date_from             = date_from or trades.first().entry_date,
            date_to               = date_to   or trades.last().entry_date,
            total_trades          = total_trades,
            winning_trades        = win_count,
            losing_trades         = loss_count,
            win_rate              = win_rate,
            gross_profit          = gross_profit,
            gross_loss            = gross_loss,
            net_profit            = net_profit,
            profit_factor         = min(profit_factor, 999.99),
            max_drawdown          = round(max_dd, 2),
            max_drawdown_amount   = round(max_dd_amt, 2),
            avg_trade             = avg_trade,
            avg_win               = avg_win,
            avg_loss              = avg_loss,
            max_consecutive_wins  = max_cw,
            max_consecutive_losses= max_cl,
        )

        return Response(
            PerformanceReportSerializer(report).data,
            status=status.HTTP_201_CREATED,
        )


# ─── Equity Curve ─────────────────────────────────────────────────────────────

class EquityCurveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        trades = _base_trades(
            request.user,
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
        )

        if not trades.exists():
            return Response([])

        equity_data    = []
        cumulative_pnl = 0.0

        for trade in trades:
            if trade.profit_loss is None:
                continue
            pnl             = float(trade.profit_loss)
            cumulative_pnl += pnl
            equity_data.append({
                "date":           trade.exit_date,
                "equity":         round(cumulative_pnl, 2),
                "daily_pnl":      round(pnl, 2),
                "cumulative_pnl": round(cumulative_pnl, 2),
            })

        return Response(equity_data)


# ─── Drawdown Analysis ────────────────────────────────────────────────────────

class DrawdownAnalysisView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        trades = _base_trades(
            request.user,
            request.query_params.get("date_from"),
            request.query_params.get("date_to"),
        )

        if not trades.exists():
            return Response({"max_drawdown": 0, "max_drawdown_amount": 0, "drawdown_data": []})

        equity_curve = []
        cumulative   = 0.0
        for trade in trades:
            if trade.profit_loss is None:
                continue
            cumulative += float(trade.profit_loss)
            equity_curve.append(cumulative)

        peak = equity_curve[0] if equity_curve else 0
        max_drawdown = max_drawdown_amount = 0.0
        drawdown_data = []

        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown     = peak - equity
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
            if drawdown > max_drawdown_amount:
                max_drawdown_amount = drawdown
                max_drawdown        = drawdown_pct
            drawdown_data.append({
                "equity":               round(equity, 2),
                "peak_equity":          round(peak, 2),
                "drawdown_amount":      round(drawdown, 2),
                "drawdown_percentage":  round(drawdown_pct, 2),
            })

        return Response({
            "max_drawdown":        round(max_drawdown, 2),
            "max_drawdown_amount": round(max_drawdown_amount, 2),
            "drawdown_data":       drawdown_data,
        })


# ─── AI-powered Insights ──────────────────────────────────────────────────────

class InsightsView(APIView):
    """
    GET  /api/analytics/insights/
        Returns the 20 most recent saved insights for the user.

    POST /api/analytics/insights/
        Triggers a fresh AI analysis of the last 30 days of trades.

        Optional body params:
          days   (int)  — look-back window in days (default 30, max 180)
          date_from / date_to — explicit date range overrides `days`

        Returns the newly generated insights.

        The view uses claude-haiku (the fastest/cheapest Anthropic model)
        via analytics/services.py — no third-party paid service is needed.
    """

    permission_classes = [permissions.IsAuthenticated]

    # ── GET ───────────────────────────────────────────────────────────────────

    def get(self, request):
        insights = (
            TradingInsight.objects
            .filter(user=request.user)
            .order_by("-created_at")[:20]
        )
        return Response(TradingInsightSerializer(insights, many=True).data)

    # ── POST ──────────────────────────────────────────────────────────────────

    def post(self, request):
        user = request.user

        # ── Date range ────────────────────────────────────────────────────────
        date_from = request.data.get("date_from")
        date_to   = request.data.get("date_to")

        # FIX: Safe casting of 'days' parameter to avoid TypeError/ValueError 
        # when frontend sends null or empty strings.
        if not date_from:
            raw_days = request.data.get("days")
            try:
                days = min(int(raw_days if raw_days not in [None, ""] else 30), 180)
            except (ValueError, TypeError):
                days = 30
            date_from = timezone.now() - timedelta(days=days)

        trades = _base_trades(user, date_from, date_to)

        if not trades.exists():
            return Response(
                {"error": "No closed trades found for this period. Add some trades first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Warn if too few trades — Claude will still try
        trade_count = trades.count()
        if trade_count < 5:
            return Response(
                {
                    "error": (
                        f"Only {trade_count} closed trade(s) found. "
                        "At least 5 are needed for meaningful insights."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Call the AI service ───────────────────────────────────────────────
        try:
            from .services import generate_ai_insights, save_insights

            raw_insights = generate_ai_insights(trades)
            saved        = save_insights(user, raw_insights)

        except RuntimeError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            return Response(
                {"error": f"Unexpected error during insight generation: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "generated":  len(saved),
                "trade_count": trade_count,
                "insights": TradingInsightSerializer(saved, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ── Acknowledge / action an insight ──────────────────────────────────────────

class InsightDetailView(APIView):
    """
    PATCH /api/analytics/insights/<pk>/
    Body: { "is_acknowledged": true }  or  { "is_actioned": true }
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            insight = TradingInsight.objects.get(pk=pk, user=request.user)
        except TradingInsight.DoesNotExist:
            return Response({"error": "Insight not found."}, status=status.HTTP_404_NOT_FOUND)

        if "is_acknowledged" in request.data:
            insight.is_acknowledged = bool(request.data["is_acknowledged"])
        if "is_actioned" in request.data:
            insight.is_actioned = bool(request.data["is_actioned"])
        insight.save()

        return Response(TradingInsightSerializer(insight).data)


# ─── Calendar Heatmap ─────────────────────────────────────────────────────────

class CalendarHeatmapView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        year = request.query_params.get("year", timezone.now().year)

        trades = Trade.objects.filter(
            user=request.user,
            status="CLOSED",
            entry_date__year=year,
        )

        daily_pnl = (
            trades
            .extra(select={"date": "DATE(entry_date)"})
            .values("date")
            .annotate(pnl=Sum("profit_loss"), trades=Count("id"))
        )

        return Response(list(daily_pnl))