from rest_framework import serializers
from .models import MT5Account, MT5TradeImport, MT5ConnectionLog, MT5SetupGuide


# ─── Account ──────────────────────────────────────────────────────────────────

class MT5AccountSerializer(serializers.ModelSerializer):
    connection_status_display = serializers.CharField(
        source='get_status_display',
        read_only=True,
    )

    class Meta:
        model  = MT5Account
        fields = [
            'id', 'name', 'account_number', 'server',
            'status', 'connection_status_display', 'last_connected', 'last_error',
            'balance', 'equity', 'margin', 'free_margin', 'margin_level',
            'auto_sync', 'sync_interval',
            'is_active', 'is_demo',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'last_connected', 'last_error',
            'balance', 'equity', 'margin', 'free_margin', 'margin_level',
            'created_at', 'updated_at',
        ]


class MT5AccountCreateSerializer(serializers.ModelSerializer):
    """
    Used for POST /api/mt5/accounts/
    Accepts credentials but never echoes them back.
    """
    password          = serializers.CharField(write_only=True, min_length=1)
    investor_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = MT5Account
        fields = [
            'name', 'account_number', 'server',
            'password', 'investor_password',
            'auto_sync', 'sync_interval', 'is_demo',
        ]

    def validate_account_number(self, value):
        """MT5 account numbers are numeric."""
        value = value.strip()
        if not value.isdigit():
            raise serializers.ValidationError("Account number must contain only digits.")
        return value

    def validate_server(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Server address is required.")
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        # Check unique_together constraint upfront for a nicer error message
        if MT5Account.objects.filter(
            user=user,
            account_number=attrs['account_number'],
            server=attrs['server'],
        ).exists():
            raise serializers.ValidationError(
                "You already have an account with this number on this server."
            )
        return attrs

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class MT5AccountUpdateSerializer(serializers.ModelSerializer):
    """Used for PATCH /api/mt5/accounts/<pk>/  – only editable fields."""
    class Meta:
        model  = MT5Account
        fields = ['name', 'auto_sync', 'sync_interval', 'is_demo']


# ─── Trade import ─────────────────────────────────────────────────────────────

class MT5TradeImportSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model  = MT5TradeImport
        fields = [
            'id', 'account', 'account_name', 'status',
            'date_from', 'date_to',
            'total_trades', 'imported_trades', 'skipped_trades', 'failed_trades',
            'error_message', 'started_at', 'completed_at', 'created_at',
            'duration_seconds',
        ]
        read_only_fields = [
            'id', 'status', 'total_trades', 'imported_trades',
            'skipped_trades', 'failed_trades', 'error_message',
            'started_at', 'completed_at', 'created_at',
        ]

    def get_duration_seconds(self, obj) -> int | None:
        if obj.started_at and obj.completed_at:
            return int((obj.completed_at - obj.started_at).total_seconds())
        return None


# ─── Connection log ───────────────────────────────────────────────────────────

class MT5ConnectionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MT5ConnectionLog
        fields = ['id', 'log_type', 'message', 'details', 'created_at']


# ─── Setup guide ──────────────────────────────────────────────────────────────

class MT5SetupGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MT5SetupGuide
        fields = ['id', 'title', 'content', 'order']


# ─── Request / action serializers ─────────────────────────────────────────────

class MT5ConnectionTestSerializer(serializers.Serializer):
    server         = serializers.CharField(required=True)
    account_number = serializers.CharField(required=True)
    password       = serializers.CharField(required=True, write_only=True)

    def validate_account_number(self, value):
        value = value.strip()
        if not value.isdigit():
            raise serializers.ValidationError("Account number must be numeric.")
        return value


class MT5SyncRequestSerializer(serializers.Serializer):
    account_id = serializers.UUIDField(required=True)
    date_from  = serializers.DateTimeField(required=False)
    date_to    = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if 'date_from' in attrs and 'date_to' in attrs:
            if attrs['date_from'] >= attrs['date_to']:
                raise serializers.ValidationError("date_from must be before date_to.")
        return attrs