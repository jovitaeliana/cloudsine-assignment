import { useRef, useState } from "react";

const MAX_BYTES = 32 * 1024 * 1024;

interface Props {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
  uploadingFilename?: string | null;
  uploadingSize?: number | null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadZone({
  onFileSelected,
  disabled,
  uploadingFilename,
  uploadingSize,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFile(file: File | undefined) {
    if (!file) return;
    if (file.size === 0) {
      setError("File is empty");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(`File is ${formatSize(file.size)} — max is 32 MB`);
      return;
    }
    setError(null);
    onFileSelected(file);
  }

  if (disabled && uploadingFilename) {
    return (
      <div className="border-2 border-dashed border-blue-300 bg-blue-50 rounded-lg p-8 text-center">
        <div className="flex items-center justify-center gap-3">
          <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <div className="text-left">
            <p className="text-blue-900 font-medium">Uploading {uploadingFilename}</p>
            {uploadingSize != null && (
              <p className="text-xs text-blue-700">{formatSize(uploadingSize)}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-8 text-center transition-all duration-150 ${
        dragging
          ? "border-blue-500 bg-blue-50 ring-4 ring-blue-200 scale-[1.01]"
          : "border-gray-300 hover:border-gray-400"
      } ${disabled ? "opacity-50 pointer-events-none" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handleFile(e.dataTransfer.files?.[0]);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0] ?? undefined)}
      />
      <p className="mb-2 text-gray-700">Drag a file here, or</p>
      <button
        type="button"
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
      >
        Choose file
      </button>
      <p className="mt-2 text-xs text-gray-500">Up to 32 MB</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  );
}
