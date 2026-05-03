import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class ExplorePage extends StatelessWidget {
  const ExplorePage({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Explore',
              style: textTheme.headlineLarge?.copyWith(
                fontWeight: FontWeight.bold,
                color: colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Choose a city to begin your audio tour',
              style: textTheme.bodyLarge?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 32),
            // Paris — active city card
            _CityCard(
              cityName: 'Paris',
              subtitle: 'The city of light, scandal, and hidden stories',
              country: 'France',
              isAvailable: true,
              gradientColors: [
                colorScheme.primary,
                colorScheme.tertiary,
              ],
              onTap: () => context.push('/plan-trip/paris'),
            ),
            const SizedBox(height: 16),
            // Coming soon cities
            _CityCard(
              cityName: 'London',
              subtitle: 'Coming soon',
              country: 'England',
              isAvailable: false,
              gradientColors: [
                colorScheme.surfaceContainerHighest,
                colorScheme.surfaceContainerHigh,
              ],
            ),
            const SizedBox(height: 16),
            _CityCard(
              cityName: 'Tokyo',
              subtitle: 'Coming soon',
              country: 'Japan',
              isAvailable: false,
              gradientColors: [
                colorScheme.surfaceContainerHighest,
                colorScheme.surfaceContainerHigh,
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CityCard extends StatelessWidget {
  final String cityName;
  final String subtitle;
  final String country;
  final bool isAvailable;
  final List<Color> gradientColors;
  final VoidCallback? onTap;

  const _CityCard({
    required this.cityName,
    required this.subtitle,
    required this.country,
    required this.isAvailable,
    required this.gradientColors,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return GestureDetector(
      onTap: isAvailable ? onTap : null,
      child: Card(
        elevation: isAvailable ? 8 : 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
        clipBehavior: Clip.antiAlias,
        child: Container(
          height: isAvailable ? 200 : 120,
          width: double.infinity,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: gradientColors,
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (!isAvailable)
                  Opacity(
                    opacity: 0.5,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          cityName,
                          style: textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: colorScheme.onSurface,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          subtitle,
                          style: textTheme.bodyMedium?.copyWith(
                            color: colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  )
                else ...[
                  Text(
                    country,
                    style: textTheme.labelLarge?.copyWith(
                      color: colorScheme.onPrimary.withValues(alpha: 0.8),
                      letterSpacing: 1.2,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    cityName,
                    style: textTheme.displaySmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: colorScheme.onPrimary,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    subtitle,
                    style: textTheme.bodyLarge?.copyWith(
                      color: colorScheme.onPrimary.withValues(alpha: 0.9),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
