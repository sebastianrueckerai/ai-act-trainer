export function Avatar({
  name,
  imageUrl,
  mood,
  size = 96,
}: {
  name: string;
  imageUrl: string | null;
  mood: string;
  size?: number;
}) {
  return (
    <div className="ui-avatar" data-mood={mood} style={{ width: size, height: size }}>
      {imageUrl ? (
        <img src={imageUrl} alt={name} width={size} height={size} />
      ) : (
        <span className="ui-avatar-fallback" role="img" aria-label={name}>
          {name.slice(0, 1)}
        </span>
      )}
    </div>
  );
}
