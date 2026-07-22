// canvas.toBlob() produces a PNG with no metadata at all, so the download would
// carry no capture date. This module rewrites the byte stream to insert the
// generation date: an `eXIf` chunk (PNG 1.5.0 / ISO 15948:2004+, read as EXIF by
// Finder, Preview, Lightroom, exiftool) and a `tEXt` "Creation Time" entry for
// viewers that ignore eXIf.

const CRC_TABLE = (() => {
	const table = new Uint32Array(256);
	for (let n = 0; n < 256; n += 1) {
		let c = n;
		for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
		table[n] = c >>> 0;
	}
	return table;
})();

function crc32(bytes: Uint8Array): number {
	let c = 0xffffffff;
	for (let i = 0; i < bytes.length; i += 1) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
	return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Uint8Array): Uint8Array {
	const chunk = new Uint8Array(12 + data.length);
	const view = new DataView(chunk.buffer);
	view.setUint32(0, data.length);
	for (let i = 0; i < 4; i += 1) chunk[4 + i] = type.charCodeAt(i);
	chunk.set(data, 8);
	view.setUint32(8 + data.length, crc32(chunk.subarray(4, 8 + data.length)));
	return chunk;
}

function pad2(value: number): string {
	return String(value).padStart(2, '0');
}

/** EXIF date form: local time, "YYYY:MM:DD HH:MM:SS". */
function exifDateString(date: Date): string {
	return `${date.getFullYear()}:${pad2(date.getMonth() + 1)}:${pad2(date.getDate())} `
		+ `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

/** EXIF offset form: "+09:00". EXIF date tags carry no zone of their own. */
function exifOffsetString(date: Date): string {
	const minutes = -date.getTimezoneOffset();
	const sign = minutes < 0 ? '-' : '+';
	const abs = Math.abs(minutes);
	return `${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`;
}

function asciiBytes(value: string, length: number): Uint8Array {
	const bytes = new Uint8Array(length);
	for (let i = 0; i < value.length && i < length - 1; i += 1) bytes[i] = value.charCodeAt(i);
	return bytes; // NUL-terminated by the zero fill
}

/**
 * Minimal little-endian TIFF stream holding the date tags only:
 *   IFD0     DateTime (0x0132), Exif IFD pointer (0x8769)
 *   Exif IFD ExifVersion, DateTimeOriginal, DateTimeDigitized,
 *            OffsetTime, OffsetTimeOriginal, OffsetTimeDigitized
 */
function exifDateBlock(date: Date): Uint8Array {
	const IFD0_ENTRIES = 2;
	const EXIF_ENTRIES = 6;
	const ifd0Offset = 8;
	const exifIfdOffset = ifd0Offset + 2 + IFD0_ENTRIES * 12 + 4;
	const dataOffset = exifIfdOffset + 2 + EXIF_ENTRIES * 12 + 4;
	const dateOffset = dataOffset;
	const offsetOffset = dateOffset + 20;
	const total = offsetOffset + 7;

	const bytes = new Uint8Array(total);
	const view = new DataView(bytes.buffer);
	const LE = true;

	// TIFF header
	bytes[0] = 0x49; bytes[1] = 0x49; // "II" little endian
	view.setUint16(2, 42, LE);
	view.setUint32(4, ifd0Offset, LE);

	let cursor = ifd0Offset;
	const writeEntry = (tag: number, type: number, count: number, write: (at: number) => void) => {
		view.setUint16(cursor, tag, LE);
		view.setUint16(cursor + 2, type, LE);
		view.setUint32(cursor + 4, count, LE);
		write(cursor + 8);
		cursor += 12;
	};
	const ASCII = 2;
	const LONG = 4;
	const UNDEFINED = 7;

	view.setUint16(cursor, IFD0_ENTRIES, LE);
	cursor += 2;
	writeEntry(0x0132, ASCII, 20, (at) => view.setUint32(at, dateOffset, LE));
	writeEntry(0x8769, LONG, 1, (at) => view.setUint32(at, exifIfdOffset, LE));
	view.setUint32(cursor, 0, LE); // no IFD1
	cursor += 4;

	view.setUint16(cursor, EXIF_ENTRIES, LE);
	cursor += 2;
	// Tags must ascend. ExifVersion "0231" fits inline in the value field.
	writeEntry(0x9000, UNDEFINED, 4, (at) => {
		bytes[at] = 0x30; bytes[at + 1] = 0x32; bytes[at + 2] = 0x33; bytes[at + 3] = 0x31;
	});
	writeEntry(0x9003, ASCII, 20, (at) => view.setUint32(at, dateOffset, LE));
	writeEntry(0x9004, ASCII, 20, (at) => view.setUint32(at, dateOffset, LE));
	writeEntry(0x9010, ASCII, 7, (at) => view.setUint32(at, offsetOffset, LE));
	writeEntry(0x9011, ASCII, 7, (at) => view.setUint32(at, offsetOffset, LE));
	writeEntry(0x9012, ASCII, 7, (at) => view.setUint32(at, offsetOffset, LE));
	view.setUint32(cursor, 0, LE);

	bytes.set(asciiBytes(exifDateString(date), 20), dateOffset);
	bytes.set(asciiBytes(exifOffsetString(date), 7), offsetOffset);
	return bytes;
}

const RFC1123_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const RFC1123_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** PNG "Creation Time" keyword expects an RFC 1123 date. */
function creationTimeChunk(date: Date): Uint8Array {
	const offset = exifOffsetString(date).replace(':', '');
	const value = `${RFC1123_DAYS[date.getDay()]}, ${pad2(date.getDate())} ${RFC1123_MONTHS[date.getMonth()]} `
		+ `${date.getFullYear()} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())} ${offset}`;
	const text = `Creation Time\0${value}`;
	const data = new Uint8Array(text.length);
	for (let i = 0; i < text.length; i += 1) data[i] = text.charCodeAt(i) & 0xff;
	return pngChunk('tEXt', data);
}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

/**
 * Return a copy of `blob` carrying `date` as its EXIF capture date. The chunks
 * go right after IHDR, which is where the spec wants eXIf. A blob that is not a
 * PNG is returned unchanged rather than corrupted.
 */
export async function withPngCaptureDate(blob: Blob, date: Date): Promise<Blob> {
	const source = new Uint8Array(await blob.arrayBuffer());
	if (source.length < 8 + 25 || PNG_SIGNATURE.some((byte, i) => source[i] !== byte)) return blob;
	const ihdrLength = new DataView(source.buffer, source.byteOffset).getUint32(8);
	const insertAt = 8 + 12 + ihdrLength;
	if (insertAt > source.length) return blob;

	const exif = pngChunk('eXIf', exifDateBlock(date));
	const creationTime = creationTimeChunk(date);
	const out = new Uint8Array(source.length + exif.length + creationTime.length);
	out.set(source.subarray(0, insertAt), 0);
	out.set(exif, insertAt);
	out.set(creationTime, insertAt + exif.length);
	out.set(source.subarray(insertAt), insertAt + exif.length + creationTime.length);
	return new Blob([out], { type: 'image/png' });
}
