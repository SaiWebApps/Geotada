import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:provider/provider.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';
import 'package:ondoway/services/auth_service.dart';
import 'package:ondoway/services/lens_service.dart';
import 'package:ondoway/services/profile_service.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _emailController = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _magicLinkSent = false;
  String? _errorMessage;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _sendMagicLink() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _errorMessage = null);

    try {
      await context.read<AuthService>().requestMagicLink(
            _emailController.text.trim(),
          );
      setState(() => _magicLinkSent = true);
    } on AuthException catch (e) {
      setState(() => _errorMessage = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final authService = context.watch<AuthService>();

    return Scaffold(
      floatingActionButton: !kReleaseMode
          ? Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                FloatingActionButton.extended(
                  heroTag: 'debug-location-spike',
                  onPressed: () => context.push('/debug/location-spike'),
                  icon: const Icon(Icons.explore),
                  label: const Text('Location Spike'),
                ),
                const SizedBox(height: 12),
                FloatingActionButton.extended(
                  heroTag: 'debug-tour-playback-proof',
                  onPressed: () => context.push('/debug/tour-playback-proof'),
                  icon: const Icon(Icons.headphones),
                  label: const Text('Tour Proof'),
                ),
              ],
            )
          : null,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 400),
              child: _magicLinkSent ? _buildCheckEmail() : _buildLoginForm(authService),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLoginForm(AuthService authService) {
    return Form(
      key: _formKey,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Ondoway',
            style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            'Your city, your story',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 48),
          TextFormField(
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'Email address',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.email_outlined),
            ),
            validator: (value) {
              if (value == null || value.trim().isEmpty) {
                return 'Please enter your email';
              }
              if (!value.contains('@') || !value.contains('.')) {
                return 'Please enter a valid email';
              }
              return null;
            },
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: authService.isLoading ? null : _sendMagicLink,
            icon: authService.isLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.mail_outline),
            label: const Text('Send Magic Link'),
          ),
          if (_errorMessage != null) ...[
            const SizedBox(height: 12),
            Text(
              _errorMessage!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
              textAlign: TextAlign.center,
            ),
          ],
          const SizedBox(height: 24),
          Row(
            children: [
              const Expanded(child: Divider()),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  'or',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
              const Expanded(child: Divider()),
            ],
          ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: authService.isLoading ? null : () => _handleGoogleSignIn(),
            icon: const Icon(Icons.g_mobiledata, size: 24),
            label: const Text('Sign in with Google'),
          ),
          if (defaultTargetPlatform == TargetPlatform.iOS) ...[
            const SizedBox(height: 12),
            SignInWithAppleButton(
              onPressed: authService.isLoading ? () {} : () => _handleAppleSignIn(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCheckEmail() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          Icons.mark_email_read_outlined,
          size: 80,
          color: Theme.of(context).colorScheme.primary,
        ),
        const SizedBox(height: 24),
        Text(
          'Check your email',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 12),
        Text(
          'We sent a sign-in link to\n${_emailController.text.trim()}',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyLarge,
        ),
        const SizedBox(height: 32),
        TextButton(
          onPressed: () => setState(() => _magicLinkSent = false),
          child: const Text('Use a different email'),
        ),
      ],
    );
  }

  Future<void> _handleGoogleSignIn() async {
    setState(() => _errorMessage = null);

    try {
      final googleSignIn = GoogleSignIn(scopes: ['email']);
      final account = await googleSignIn.signIn();
      if (account == null) return; // user cancelled

      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null) {
        setState(() => _errorMessage = 'Failed to get Google credentials');
        return;
      }

      if (!mounted) return;
      await context.read<AuthService>().loginWithGoogle(idToken);

      if (!mounted) return;
      final authService = context.read<AuthService>();
      final lensService = context.read<LensService>();
      final profileService = context.read<ProfileService>();

      await Future.wait([
        if (!lensService.isLoaded) lensService.fetchLenses(),
        profileService.fetchProfile(authService.accessToken!),
      ]);

      if (mounted) {
        context.go(profileService.isFirstTime ? '/onboarding' : '/explore');
      }
    } on AuthException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Google sign-in failed: $e');
    }
  }

  Future<void> _handleAppleSignIn() async {
    setState(() => _errorMessage = null);

    try {
      if (!mounted) return;
      await context.read<AuthService>().loginWithApple();

      if (!mounted) return;
      final authService = context.read<AuthService>();
      final lensService = context.read<LensService>();
      final profileService = context.read<ProfileService>();

      await Future.wait([
        if (!lensService.isLoaded) lensService.fetchLenses(),
        profileService.fetchProfile(authService.accessToken!),
      ]);

      if (mounted) {
        context.go(profileService.isFirstTime ? '/onboarding' : '/explore');
      }
    } on AuthException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Apple sign-in failed: $e');
    }
  }
}
