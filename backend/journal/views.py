from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from .models import JournalEntry, TradingGoal, TradingPlan, ChecklistTemplate, TradeChecklist
from .serializers import (
    JournalEntrySerializer, TradingGoalSerializer,
    TradingPlanSerializer, ChecklistTemplateSerializer,
    TradeChecklistSerializer
)


class JournalEntryListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JournalEntrySerializer
    
    def get_queryset(self):
        queryset = JournalEntry.objects.filter(user=self.request.user)
        
        # Filter by entry type
        entry_type = self.request.query_params.get('entry_type')
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            queryset = queryset.filter(entry_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(entry_date__lte=date_to)
        
        # Filter by tags
        tags = self.request.query_params.get('tags')
        if tags:
            tag_list = tags.split(',')
            for tag in tag_list:
                queryset = queryset.filter(tags__contains=[tag.strip()])
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class JournalEntryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JournalEntrySerializer
    
    def get_queryset(self):
        return JournalEntry.objects.filter(user=self.request.user)


class TradingGoalListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradingGoalSerializer
    
    def get(self, request, *args, **kwargs):
        # Sync all active goals with latest trade data before listing them
        active_goals = TradingGoal.objects.filter(user=request.user, status='ACTIVE')
        for goal in active_goals:
            goal.update_progress()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return TradingGoal.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TradingGoalDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradingGoalSerializer
    
    def get_queryset(self):
        return TradingGoal.objects.filter(user=self.request.user)

    def get_object(self):
        # Sync this specific goal before returning it
        obj = super().get_object()
        obj.update_progress()
        return obj
    
    def perform_update(self, serializer):
        instance = serializer.save()
        # Progress calculation is now centralized in the model
        instance.update_progress()


class TradingPlanListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradingPlanSerializer
    
    def get_queryset(self):
        return TradingPlan.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TradingPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TradingPlanSerializer
    
    def get_queryset(self):
        return TradingPlan.objects.filter(user=self.request.user)


class ChecklistTemplateListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChecklistTemplateSerializer
    
    def get_queryset(self):
        return ChecklistTemplate.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ChecklistTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChecklistTemplateSerializer
    
    def get_queryset(self):
        return ChecklistTemplate.objects.filter(user=self.request.user)


class TradeChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, trade_id):
        try:
            checklist = TradeChecklist.objects.get(trade_id=trade_id)
            return Response(TradeChecklistSerializer(checklist).data)
        except TradeChecklist.DoesNotExist:
            return Response(
                {'error': 'Checklist not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request, trade_id):
        serializer = TradeChecklistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(trade_id=trade_id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    def patch(self, request, trade_id):
        try:
            checklist = TradeChecklist.objects.get(trade_id=trade_id)
            serializer = TradeChecklistSerializer(
                checklist,
                data=request.data,
                partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        except TradeChecklist.DoesNotExist:
            return Response(
                {'error': 'Checklist not found.'},
                status=status.HTTP_404_NOT_FOUND
            )


class JournalSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        # Sync all active goals before counting/returning them in the summary
        active_goals_qs = TradingGoal.objects.filter(user=user, status='ACTIVE')
        for goal in active_goals_qs:
            goal.update_progress()
            
        # Get counts
        total_entries = JournalEntry.objects.filter(user=user).count()
        
        # Recent entries
        recent_entries = JournalEntry.objects.filter(
            user=user
        ).order_by('-entry_date')[:5]
        
        # Active goals count
        active_goals = TradingGoal.objects.filter(
            user=user,
            status='ACTIVE'
        ).count()
        
        # Goals nearing deadline (within 7 days)
        from datetime import timedelta
        nearing_deadline = TradingGoal.objects.filter(
            user=user,
            status='ACTIVE',
            target_date__lte=timezone.now().date() + timedelta(days=7)
        ).count()
        
        return Response({
            'total_entries': total_entries,
            'recent_entries': JournalEntrySerializer(
                recent_entries,
                many=True
            ).data,
            'active_goals': active_goals,
            'goals_nearing_deadline': nearing_deadline,
        })