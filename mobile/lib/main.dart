import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/router.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final authService = AuthService();
  final lensService = LensService();
  final profileService = ProfileService();

  await authService.tryRestoreSession();

  if (authService.isAuthenticated) {
    try {
      await Future.wait([
        lensService.fetchLenses(),
        profileService.fetchProfile(
          authService.userId!,
          authService.accessToken!,
        ),
      ]);
    } catch (_) {
      // Non-fatal: app still works, onboarding detection may default to first-time
    }
  }

  final router = createRouter(authService, profileService, lensService);

  final appLinks = AppLinks();
  appLinks.uriLinkStream.listen((uri) {
    final host = uri.host;
    final path = uri.path;
    final fullPath = host.isNotEmpty ? '/$host$path' : path;
    final query = uri.query.isNotEmpty ? '?${uri.query}' : '';
    debugPrint('DEEP LINK: $uri → routing to $fullPath$query');
    router.go('$fullPath$query');
  });

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: authService),
        ChangeNotifierProvider.value(value: lensService),
        ChangeNotifierProvider.value(value: profileService),
      ],
      child: OndowayApp(router: router),
    ),
  );
}

class OndowayApp extends StatelessWidget {
  final dynamic router;
  const OndowayApp({super.key, required this.router});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Ondoway',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF3D5AFE),
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF121212),
      ),
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
