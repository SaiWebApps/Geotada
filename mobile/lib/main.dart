import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/router.dart';
import 'package:ondoway/services/auth_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final authService = AuthService();
  await authService.tryRestoreSession();

  runApp(
    ChangeNotifierProvider.value(
      value: authService,
      child: const OndowayApp(),
    ),
  );
}

class OndowayApp extends StatelessWidget {
  const OndowayApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Ondoway',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      routerConfig: createRouter(context.read<AuthService>()),
      debugShowCheckedModeBanner: false,
    );
  }
}
