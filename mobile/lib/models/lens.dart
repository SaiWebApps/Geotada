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

  /// Parses one lens (parent or child) from the public `GET /api/v1/lenses`
  /// response, where each lens is a flat object `{id, name, display_label,
  /// is_parent}` (parents additionally carry a `children` list, handled by the
  /// caller). Replaces the old graph-node shape (`{id, properties: {...}}`).
  factory Lens.fromApiJson(Map<String, dynamic> json) {
    return Lens(
      id: json['id'] as String,
      name: json['name'] as String? ?? '',
      displayLabel: json['display_label'] as String? ?? '',
      isParent: json['is_parent'] as bool? ?? false,
    );
  }
}
