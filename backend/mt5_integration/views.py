import logging
import platform
from datetime import timedelta

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from trades.models import Trade
from .models import MT5Account, MT5TradeImport, MT5ConnectionLog, MT5SetupGuide
from .serializers import (
    MT5AccountSerializer, MT5AccountCreateSerializer, MT5AccountUpdateSerializer,
    MT5TradeImportSerializer, MT5ConnectionLogSerializer,
    MT5SetupGuideSerializer, MT5ConnectionTestSerializer,
    MT5SyncRequestSerializer,
)
from .services import (
    MT5Service, MT5TradeImporter,
    MT5Error, MT5NotAvailableError, MT5AuthError,
    MT5_AVAILABLE,
)

logger = logging.getLogger(__name__)


# ─── Accounts ─────────────────────────────────────────────────────────────────

class MT5AccountListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return MT5AccountCreateSerializer if self.request.method == 'POST' else MT5AccountSerializer

    def get_queryset(self):
        return MT5Account.objects.filter(user=self.request.user, is_active=True)

    def create(self, request, *args, **kwargs):
        serializer = MT5AccountCreateSerializer(
            data=request.data,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        account = serializer.save()
        return Response(
            MT5AccountSerializer(account).data,
            status=status.HTTP_201_CREATED,
        )


class MT5AccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return MT5AccountUpdateSerializer
        return MT5AccountSerializer

    def get_queryset(self):
        return MT5Account.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active'])


# ─── Connection test ──────────────────────────────────────────────────────────

class MT5ConnectionTestView(APIView):
    """
    POST /api/mt5/test-connection/
    On Linux returns a helpful 503 explaining the Windows-only restriction.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Fast-fail on non-Windows before even validating
        if not MT5_AVAILABLE:
            return Response(
                {
                    'success': False,
                    'code':    'MT5_NOT_AVAILABLE',
                    'error':   (
                        f"Direct MT5 connection is not available on {platform.system()}. "
                        "The MetaTrader5 Python library only works on Windows. "
                        "Use the file-based import instead: export a Detailed Report "
                        "from MT5 (History tab → right-click → Save as Detailed Report) "
                        "and upload it via POST /api/mt5/import-file/."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = MT5ConnectionTestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        temp = MT5Account(
            account_number=data['account_number'],
            server=data['server'],
            password=data['password'],
        )
        try:
            with MT5Service(temp) as svc:
                info = svc.get_account_info()
            return Response({'success': True, 'message': 'Connection successful.', 'account_info': info})

        except MT5AuthError as exc:
            return Response({'success': False, 'error': str(exc), 'code': 'AUTH_FAILED'}, status=401)
        except MT5Error as exc:
            return Response({'success': False, 'error': str(exc), 'code': 'MT5_ERROR'}, status=502)
        except Exception as exc:
            logger.error("MT5 connection test: %s", exc, exc_info=True)
            return Response({'success': False, 'error': 'Unexpected server error.'}, status=500)


# ─── Direct sync (Windows only) ───────────────────────────────────────────────

class MT5SyncTradesView(APIView):
    """
    POST /api/mt5/sync/
    Connects directly to MT5 terminal.  Windows only.
    On Linux → 503 with instructions to use /api/mt5/import-file/ instead.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not MT5_AVAILABLE:
            return Response(
                {
                    'error': (
                        f"Direct MT5 sync is not supported on {platform.system()}. "
                        "Export a Detailed Report from MT5 and upload it via "
                        "POST /api/mt5/import-file/  (multipart/form-data, field name: file)."
                    ),
                    'code':           'MT5_NOT_AVAILABLE',
                    'import_url':     '/api/mt5/import-file/',
                    'export_steps': [
                        "Open MT5 → press Ctrl+T to open Terminal",
                        "Click the 'History' tab",
                        "Right-click inside the history area",
                        "Choose 'Save as Detailed Report'",
                        "Save as HTML (preferred) or CSV",
                        "Upload the file to POST /api/mt5/import-file/",
                    ],
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = MT5SyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            account = MT5Account.objects.get(id=data['account_id'], user=request.user, is_active=True)
        except MT5Account.DoesNotExist:
            return Response({'error': 'Account not found.'}, status=status.HTTP_404_NOT_FOUND)

        date_to   = data.get('date_to',   timezone.now())
        date_from = data.get('date_from', date_to - timedelta(days=30))

        import_record = MT5TradeImport.objects.create(
            user=request.user, account=account, status='RUNNING',
            date_from=date_from, date_to=date_to, started_at=timezone.now(),
        )
        try:
            stats = MT5TradeImporter(request.user, account, import_record).run_direct(date_from, date_to)
            return Response({
                'message': f"Sync complete. {stats['imported']} imported, {stats['skipped']} skipped.",
                'stats':   stats,
                'import':  MT5TradeImportSerializer(import_record).data,
            })

        except MT5NotAvailableError as exc:
            return Response({'error': str(exc), 'code': 'MT5_NOT_AVAILABLE'}, status=503)
        except MT5AuthError as exc:
            return Response({'error': str(exc), 'code': 'AUTH_FAILED'}, status=401)
        except MT5Error as exc:
            return Response({'error': str(exc), 'code': 'MT5_ERROR'}, status=502)
        except Exception as exc:
            logger.error("MT5 sync: %s", exc, exc_info=True)
            return Response({'error': 'Unexpected server error.'}, status=500)


# ─── File-based import (any OS) ───────────────────────────────────────────────

class MT5FileImportView(APIView):
    """
    POST /api/mt5/import-file/
    Upload a Detailed Report exported from MT5's History tab.

    Form fields:
        file        — the HTML or CSV report file (required)
        account_id  — UUID of the MT5Account to link trades to (required)
        format      — 'html' (default) or 'csv'
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        account_id = request.data.get('account_id')
        file_obj   = request.FILES.get('file')
        fmt        = request.data.get('format', 'html').lower()

        if not account_id:
            return Response({'error': 'account_id is required.'}, status=400)
        if not file_obj:
            return Response({'error': 'No file uploaded. Send a multipart file field named "file".'}, status=400)
        if fmt not in ('html', 'csv'):
            return Response({'error': 'format must be "html" or "csv".'}, status=400)

        try:
            account = MT5Account.objects.get(id=account_id, user=request.user, is_active=True)
        except MT5Account.DoesNotExist:
            return Response({'error': 'Account not found.'}, status=404)

        # Read file content (MT5 reports are small — safe to read in memory)
        try:
            content = file_obj.read().decode('utf-8', errors='replace')
        except Exception as exc:
            return Response({'error': f'Could not read file: {exc}'}, status=400)

        if not content.strip():
            return Response({'error': 'Uploaded file is empty.'}, status=400)

        import_record = MT5TradeImport.objects.create(
            user=request.user, account=account, status='RUNNING',
            started_at=timezone.now(),
        )
        try:
            stats = MT5TradeImporter(request.user, account, import_record).run_from_file(content, fmt)
            return Response({
                'message': f"Import complete. {stats['imported']} imported, {stats['skipped']} skipped.",
                'stats':   stats,
                'import':  MT5TradeImportSerializer(import_record).data,
            })

        except Exception as exc:
            return Response({'error': str(exc)}, status=500)


# ─── Open positions (Windows only) ───────────────────────────────────────────

class MT5OpenPositionsView(APIView):
    """GET /api/mt5/accounts/<account_id>/positions/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, account_id):
        if not MT5_AVAILABLE:
            return Response(
                {'error': 'Live positions require Windows + MT5 terminal.', 'code': 'MT5_NOT_AVAILABLE'},
                status=503,
            )
        try:
            account = MT5Account.objects.get(id=account_id, user=request.user, is_active=True)
        except MT5Account.DoesNotExist:
            return Response({'error': 'Account not found.'}, status=404)

        try:
            with MT5Service(account) as svc:
                positions = svc.get_open_positions()
            for p in positions:
                for k in ('volume', 'entry_price', 'current_price', 'sl', 'tp', 'profit', 'swap'):
                    if p.get(k) is not None:
                        p[k] = str(p[k])
                if p.get('open_time'):
                    p['open_time'] = p['open_time'].isoformat()
            return Response({'positions': positions, 'count': len(positions)})

        except MT5AuthError as exc:
            return Response({'error': str(exc), 'code': 'AUTH_FAILED'}, status=401)
        except MT5Error as exc:
            return Response({'error': str(exc), 'code': 'MT5_ERROR'}, status=502)


# ─── Disconnect ───────────────────────────────────────────────────────────────

class MT5DisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, account_id):
        try:
            account = MT5Account.objects.get(id=account_id, user=request.user)
        except MT5Account.DoesNotExist:
            return Response({'error': 'Account not found.'}, status=404)

        account.status = 'DISCONNECTED'
        account.save(update_fields=['status'])
        MT5ConnectionLog.objects.create(
            account=account, log_type='DISCONNECT',
            message='Disconnected by user.',
        )
        return Response({'message': 'Account disconnected successfully.'})


# ─── Import history ───────────────────────────────────────────────────────────

class MT5ImportHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = MT5TradeImportSerializer

    def get_queryset(self):
        return MT5TradeImport.objects.filter(user=self.request.user)


# ─── Connection logs ──────────────────────────────────────────────────────────

class MT5ConnectionLogsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = MT5ConnectionLogSerializer

    def get_queryset(self):
        qs         = MT5ConnectionLog.objects.filter(account__user=self.request.user)
        account_id = self.request.query_params.get('account_id')
        if account_id:
            qs = qs.filter(account_id=account_id)
        return qs[:100]


# ─── Setup guide ──────────────────────────────────────────────────────────────

class MT5SetupGuideView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class   = MT5SetupGuideSerializer

    def get_queryset(self):
        return MT5SetupGuide.objects.filter(is_active=True)


# ─── Dashboard stats ──────────────────────────────────────────────────────────

class MT5DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        accounts       = MT5Account.objects.filter(user=request.user, is_active=True)
        recent_imports = MT5TradeImport.objects.filter(user=request.user).order_by('-created_at')[:5]
        mt5_trades     = Trade.objects.filter(user=request.user, mt5_ticket__isnull=False).count()

        return Response({
            'total_accounts':        accounts.count(),
            'connected_accounts':    accounts.filter(status='CONNECTED').count(),
            'total_trades_imported': mt5_trades,
            'mt5_available':         MT5_AVAILABLE,
            'server_os':             platform.system(),
            'import_method':         'direct' if MT5_AVAILABLE else 'file_upload',
            'accounts':              MT5AccountSerializer(accounts, many=True).data,
            'recent_imports':        MT5TradeImportSerializer(recent_imports, many=True).data,
        })


# ─── Manual import guide ──────────────────────────────────────────────────────

class MT5ManualImportGuideView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            'title':      'MT5 Trade Import Guide',
            'mt5_direct_available': MT5_AVAILABLE,
            'recommended_method':   'direct' if MT5_AVAILABLE else 'file_upload',
            'steps': [
                {
                    'step': 1,
                    'title': 'Export from MT5',
                    'details': [
                        'Open MetaTrader 5',
                        'Press Ctrl+T to open Terminal',
                        "Click the 'History' tab",
                        'Right-click inside history → Save as Detailed Report',
                        'Save as HTML (preferred) or CSV',
                    ],
                },
                {
                    'step': 2,
                    'title': 'Upload to Trading Journal',
                    'details': [
                        'Go to MT5 Integration → Import File',
                        'Select your account',
                        'Choose your HTML or CSV file',
                        'Click Import',
                    ],
                },
            ],
        })