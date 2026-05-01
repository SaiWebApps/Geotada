import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/main.dart';
import 'package:ondoway/services/auth_service.dart';
import 'services/auth_service_test.dart';

void main() {
  testWidgets('OndowayApp renders login page when unauthenticated', (tester) async {
    final authService = AuthService(
      storage: FakeSecureStorage(),
      httpClient: MockClient((r) async => http.Response('', 200)),
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<AuthService>.value(
        value: authService,
        child: const OndowayApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ondoway'), findsOneWidget);
  });
}
