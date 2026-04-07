from rest_framework import serializers
from .models import (
    JournalEntry, TradingGoal, TradingPlan,
    ChecklistTemplate, TradeChecklist
)


class JournalEntrySerializer(serializers.ModelSerializer):
    related_trade_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_type', 'title', 'content',
            'related_trades', 'related_trade_ids',
            'pre_trading_mood', 'post_trading_mood',
            'tags', 'attachments', 'entry_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        related_trade_ids = validated_data.pop('related_trade_ids', [])
        entry = super().create(validated_data)
        
        if related_trade_ids:
            entry.related_trades.set(related_trade_ids)
        
        return entry


class TradingGoalSerializer(serializers.ModelSerializer):
    days_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = TradingGoal
        fields = [
            'id', 'goal_type', 'title', 'description',
            'target_value', 'current_value', 'start_date',
            'target_date', 'completed_date', 'status',
            'progress_percentage', 'days_remaining',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_days_remaining(self, obj):
        from datetime import date
        if obj.target_date and obj.status == 'ACTIVE':
            remaining = (obj.target_date - date.today()).days
            return max(0, remaining)
        return 0


class TradingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingPlan
        fields = [
            'id', 'name', 'description', 'entry_criteria',
            'exit_criteria', 'risk_management_rules',
            'position_sizing', 'markets_traded', 'timeframes',
            'pre_trading_routine', 'post_trading_routine',
            'max_risk_per_trade', 'max_daily_loss',
            'max_weekly_loss', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistTemplate
        fields = [
            'id', 'name', 'description', 'items',
            'is_pre_trade', 'is_post_trade',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TradeChecklistSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    
    class Meta:
        model = TradeChecklist
        fields = [
            'id', 'trade', 'template', 'template_name',
            'completed_items', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']