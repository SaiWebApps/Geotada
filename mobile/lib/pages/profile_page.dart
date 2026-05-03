import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:ondoway/services/auth_service.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    final authService = context.watch<AuthService>();

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.person_outline, size: 64, color: Color(0xFF9E9E9E)),
            const SizedBox(height: 16),
            if (authService.userEmail != null) ...[
              Text(
                authService.userEmail!,
                style: const TextStyle(color: Colors.white, fontSize: 16),
              ),
              const SizedBox(height: 24),
            ],
            OutlinedButton.icon(
              onPressed: () => authService.logout(),
              icon: const Icon(Icons.logout),
              label: const Text('Log out'),
            ),
          ],
        ),
      ),
    );
  }
}
