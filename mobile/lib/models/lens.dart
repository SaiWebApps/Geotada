class Lens {
  final String id;
  final String name;
  final String displayLabel;
  final bool isParent;

  const Lens({
    required this.id,
    required this.name,
    required this.displayLabel,
    required this.isParent,
  });

  factory Lens.fromApiJson(Map<String, dynamic> json) {
    final props = json['properties'] as Map<String, dynamic>? ?? {};
    return Lens(
      id: json['id'] as String,
      name: props['name'] as String? ?? '',
      displayLabel: props['display_label'] as String? ?? '',
      isParent: props['is_parent'] as bool? ?? false,
    );
  }
}
