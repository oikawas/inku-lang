/**
 * The shooting facts of an image's Exif, read in the browser.
 *
 * The image tab writes them into the source note, which is saved with the
 * work and shown to whoever the work is shared with. So only the shooting
 * facts are read: the GPS directory is never opened, and the location never
 * reaches the note (the author's choice, 2026-10-25).
 *
 * Exif is a TIFF structure. It sits in a JPEG's APP1 segment after
 * `Exif\0\0`, in a PNG's `eXIf` chunk, and is the whole file of a TIFF. GIF
 * has none. Anything unreadable gives null rather than an error: a note
 * without Exif is still a note.
 */

export type ExifFacts = {
	takenAt?: string;
	make?: string;
	model?: string;
	lens?: string;
	fNumber?: number;
	/** Seconds. */
	exposureTime?: number;
	iso?: number;
	/** Millimetres. */
	focalLength?: number;
};

const TAG_MAKE = 0x010f;
const TAG_MODEL = 0x0110;
const TAG_DATE_TIME = 0x0132;
const TAG_EXIF_IFD = 0x8769;
const TAG_EXPOSURE_TIME = 0x829a;
const TAG_F_NUMBER = 0x829d;
const TAG_ISO = 0x8827;
const TAG_DATE_TIME_ORIGINAL = 0x9003;
const TAG_FOCAL_LENGTH = 0x920a;
const TAG_LENS_MODEL = 0xa434;

// TIFF field types and their byte sizes.
const TYPE_SIZES: Record<number, number> = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 };

type Entry = { type: number; count: number; valueOffset: number };

class Tiff {
	private readonly view: DataView;
	private readonly little: boolean;
	constructor(view: DataView) {
		this.view = view;
		const order = view.getUint16(0);
		if (order === 0x4949) this.little = true;
		else if (order === 0x4d4d) this.little = false;
		else throw new Error('not a TIFF header');
		if (this.u16(2) !== 42) throw new Error('not a TIFF header');
	}

	u16(at: number): number { return this.view.getUint16(at, this.little); }
	u32(at: number): number { return this.view.getUint32(at, this.little); }
	firstIfd(): number { return this.u32(4); }

	/** The entries of one IFD, by tag. Entries that point outside the data are dropped. */
	entries(at: number): Map<number, Entry> {
		const found = new Map<number, Entry>();
		if (at <= 0 || at + 2 > this.view.byteLength) return found;
		const count = this.u16(at);
		for (let i = 0; i < count; i += 1) {
			const entryAt = at + 2 + i * 12;
			if (entryAt + 12 > this.view.byteLength) break;
			const type = this.u16(entryAt + 2);
			const valueCount = this.u32(entryAt + 4);
			const size = (TYPE_SIZES[type] ?? 0) * valueCount;
			if (size === 0) continue;
			// Values of four bytes or fewer are stored in the entry itself.
			const valueOffset = size <= 4 ? entryAt + 8 : this.u32(entryAt + 8);
			if (valueOffset + size > this.view.byteLength) continue;
			found.set(this.u16(entryAt), { type, count: valueCount, valueOffset });
		}
		return found;
	}

	text(entry: Entry | undefined): string | undefined {
		if (!entry || entry.type !== 2) return undefined;
		const bytes = new Uint8Array(this.view.buffer, this.view.byteOffset + entry.valueOffset, entry.count);
		const end = bytes.indexOf(0);
		const value = new TextDecoder('utf-8').decode(end >= 0 ? bytes.subarray(0, end) : bytes).trim();
		return value || undefined;
	}

	number(entry: Entry | undefined): number | undefined {
		if (!entry) return undefined;
		const at = entry.valueOffset;
		switch (entry.type) {
			case 3: return this.u16(at);
			case 4: return this.u32(at);
			case 9: return this.view.getInt32(at, this.little);
			case 5:
			case 10: {
				const numerator = entry.type === 5 ? this.u32(at) : this.view.getInt32(at, this.little);
				const denominator = entry.type === 5 ? this.u32(at + 4) : this.view.getInt32(at + 4, this.little);
				return denominator === 0 ? undefined : numerator / denominator;
			}
			default: return undefined;
		}
	}
}

function factsFromTiff(view: DataView): ExifFacts | null {
	const tiff = new Tiff(view);
	const ifd0 = tiff.entries(tiff.firstIfd());
	const exifAt = tiff.number(ifd0.get(TAG_EXIF_IFD));
	const exif = exifAt ? tiff.entries(exifAt) : new Map<number, Entry>();
	const facts: ExifFacts = {
		takenAt: tiff.text(exif.get(TAG_DATE_TIME_ORIGINAL)) ?? tiff.text(ifd0.get(TAG_DATE_TIME)),
		make: tiff.text(ifd0.get(TAG_MAKE)),
		model: tiff.text(ifd0.get(TAG_MODEL)),
		lens: tiff.text(exif.get(TAG_LENS_MODEL)),
		fNumber: tiff.number(exif.get(TAG_F_NUMBER)),
		exposureTime: tiff.number(exif.get(TAG_EXPOSURE_TIME)),
		iso: tiff.number(exif.get(TAG_ISO)),
		focalLength: tiff.number(exif.get(TAG_FOCAL_LENGTH)),
	};
	for (const key of Object.keys(facts) as (keyof ExifFacts)[]) {
		const value = facts[key];
		if (value === undefined || (typeof value === 'number' && !(Number.isFinite(value) && value > 0))) delete facts[key];
	}
	return Object.keys(facts).length > 0 ? facts : null;
}

function jpegExif(view: DataView): DataView | null {
	let at = 2;
	while (at + 4 <= view.byteLength) {
		if (view.getUint8(at) !== 0xff) return null;
		const marker = view.getUint8(at + 1);
		// Start of scan or end of image: the metadata segments are behind us.
		if (marker === 0xda || marker === 0xd9) return null;
		const length = view.getUint16(at + 2);
		const body = at + 4;
		if (marker === 0xe1 && length >= 8 && body + 6 <= view.byteLength
			&& view.getUint32(body) === 0x45786966 && view.getUint16(body + 4) === 0) {
			const start = body + 6;
			const end = Math.min(at + 2 + length, view.byteLength);
			return new DataView(view.buffer, view.byteOffset + start, end - start);
		}
		at += 2 + length;
	}
	return null;
}

function pngExif(view: DataView): DataView | null {
	let at = 8;
	while (at + 8 <= view.byteLength) {
		const length = view.getUint32(at);
		const type = view.getUint32(at + 4);
		const body = at + 8;
		if (type === 0x65584966 /* eXIf */) {
			if (body + length > view.byteLength) return null;
			return new DataView(view.buffer, view.byteOffset + body, length);
		}
		if (type === 0x49454e44 /* IEND */) return null;
		at = body + length + 4;
	}
	return null;
}

/** The shooting facts of a JPEG, PNG or TIFF, or null when there are none. */
export function readExifFacts(bytes: ArrayBuffer): ExifFacts | null {
	try {
		const view = new DataView(bytes);
		if (view.byteLength < 8) return null;
		let tiff: DataView | null = null;
		if (view.getUint16(0) === 0xffd8) tiff = jpegExif(view);
		else if (view.getUint32(0) === 0x89504e47) tiff = pngExif(view);
		else if (view.getUint16(0) === 0x4949 || view.getUint16(0) === 0x4d4d) tiff = view;
		return tiff ? factsFromTiff(tiff) : null;
	} catch {
		return null;
	}
}
