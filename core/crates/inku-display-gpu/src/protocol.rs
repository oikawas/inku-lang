//! The pipe between the macOS app and `inku-display-gpu`: the app writes one request
//! to the program's standard input and reads one response from its standard output,
//! then the next. Little-endian; the app's reader is `DisplayGPUProcess.swift`.
//!
//! Request: `IKG1`, the SVG's SHA-256 (32 bytes), the window (full width, full
//! height, x, y, width, height: six u32), the SVG's length (u64) and its UTF-8.
//! Length 0 asks for the scene of an SVG sent earlier with the same digest.
//!
//! Response: `IKG1` and a status byte. 0: the window's width, height and stride
//! (three u32), the pixel byte count (u64) and premultiplied RGBA8 pixels.
//! 1: a failure code and message (each a u32 length and UTF-8). 2: no scene for
//! the digest (send the SVG again).

use std::io::{self, Read, Write};

pub const MAGIC: [u8; 4] = *b"IKG1";
/// Above the display's own SVG limit, which the program applies when it reads one.
pub const MAX_SVG_BYTES: u64 = 64 * 1024 * 1024;
/// The display's largest window (`MAX_RASTER_PIXELS`) in RGBA8.
pub const MAX_PIXEL_BYTES: u64 = 16_777_216 * 4;
const MAX_TEXT_BYTES: u32 = 64 * 1024;

const IMAGE: u8 = 0;
const FAILURE: u8 = 1;
const SCENE_MISSING: u8 = 2;

/// A window on a canvas `full_width` × `full_height` pixels (the core's `DisplayRegion`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Region {
    pub full_width: u32,
    pub full_height: u32,
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Request {
    pub digest: [u8; 32],
    pub region: Region,
    /// `None` asks for the scene of the SVG sent earlier with this digest.
    pub svg: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Response {
    Image {
        width: u32,
        height: u32,
        stride: u32,
        pixels: Vec<u8>,
    },
    Failure {
        code: String,
        message: String,
    },
    SceneMissing,
}

/// The next request, or `None` when the app closed the pipe between requests.
pub fn read_request(reader: &mut impl Read) -> io::Result<Option<Request>> {
    let mut magic = [0; 4];
    loop {
        match reader.read(&mut magic[..1]) {
            Ok(0) => return Ok(None),
            Ok(_) => break,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
            Err(error) => return Err(error),
        }
    }
    reader.read_exact(&mut magic[1..])?;
    check_magic(magic)?;
    let mut digest = [0; 32];
    reader.read_exact(&mut digest)?;
    let mut values = [0; 6];
    for value in &mut values {
        *value = read_u32(reader)?;
    }
    let [full_width, full_height, x, y, width, height] = values;
    let length = read_u64(reader)?;
    if length > MAX_SVG_BYTES {
        return Err(invalid(format!("SVG of {length} bytes")));
    }
    let svg = match length {
        0 => None,
        _ => Some(read_text(reader, length as usize)?),
    };
    Ok(Some(Request {
        digest,
        region: Region {
            full_width,
            full_height,
            x,
            y,
            width,
            height,
        },
        svg,
    }))
}

pub fn write_request(writer: &mut impl Write, request: &Request) -> io::Result<()> {
    writer.write_all(&MAGIC)?;
    writer.write_all(&request.digest)?;
    let region = request.region;
    for value in [
        region.full_width,
        region.full_height,
        region.x,
        region.y,
        region.width,
        region.height,
    ] {
        writer.write_all(&value.to_le_bytes())?;
    }
    let svg = request.svg.as_deref().unwrap_or_default();
    writer.write_all(&(svg.len() as u64).to_le_bytes())?;
    writer.write_all(svg.as_bytes())?;
    writer.flush()
}

pub fn read_response(reader: &mut impl Read) -> io::Result<Response> {
    let mut magic = [0; 4];
    reader.read_exact(&mut magic)?;
    check_magic(magic)?;
    let mut status = [0; 1];
    reader.read_exact(&mut status)?;
    match status[0] {
        IMAGE => {
            let (width, height, stride) = (read_u32(reader)?, read_u32(reader)?, read_u32(reader)?);
            let length = read_u64(reader)?;
            if length > MAX_PIXEL_BYTES
                || u64::from(stride) < u64::from(width) * 4
                || length != u64::from(stride) * u64::from(height)
            {
                return Err(invalid(format!(
                    "image {width}x{height} stride {stride} with {length} bytes"
                )));
            }
            let mut pixels = vec![0; length as usize];
            reader.read_exact(&mut pixels)?;
            Ok(Response::Image {
                width,
                height,
                stride,
                pixels,
            })
        }
        FAILURE => {
            let code = read_short_text(reader)?;
            let message = read_short_text(reader)?;
            Ok(Response::Failure { code, message })
        }
        SCENE_MISSING => Ok(Response::SceneMissing),
        other => Err(invalid(format!("status {other}"))),
    }
}

pub fn write_response(writer: &mut impl Write, response: &Response) -> io::Result<()> {
    writer.write_all(&MAGIC)?;
    match response {
        Response::Image {
            width,
            height,
            stride,
            pixels,
        } => {
            writer.write_all(&[IMAGE])?;
            for value in [width, height, stride] {
                writer.write_all(&value.to_le_bytes())?;
            }
            writer.write_all(&(pixels.len() as u64).to_le_bytes())?;
            writer.write_all(pixels)?;
        }
        Response::Failure { code, message } => {
            writer.write_all(&[FAILURE])?;
            for text in [code, message] {
                let text = shortened(text);
                writer.write_all(&(text.len() as u32).to_le_bytes())?;
                writer.write_all(text.as_bytes())?;
            }
        }
        Response::SceneMissing => writer.write_all(&[SCENE_MISSING])?,
    }
    writer.flush()
}

fn check_magic(magic: [u8; 4]) -> io::Result<()> {
    if magic == MAGIC {
        Ok(())
    } else {
        Err(invalid(format!("magic {magic:?}")))
    }
}

fn read_u32(reader: &mut impl Read) -> io::Result<u32> {
    let mut bytes = [0; 4];
    reader.read_exact(&mut bytes)?;
    Ok(u32::from_le_bytes(bytes))
}

fn read_u64(reader: &mut impl Read) -> io::Result<u64> {
    let mut bytes = [0; 8];
    reader.read_exact(&mut bytes)?;
    Ok(u64::from_le_bytes(bytes))
}

fn read_text(reader: &mut impl Read, length: usize) -> io::Result<String> {
    let mut bytes = vec![0; length];
    reader.read_exact(&mut bytes)?;
    String::from_utf8(bytes).map_err(|_| invalid("text is not UTF-8".to_owned()))
}

fn read_short_text(reader: &mut impl Read) -> io::Result<String> {
    let length = read_u32(reader)?;
    if length > MAX_TEXT_BYTES {
        return Err(invalid(format!("text of {length} bytes")));
    }
    read_text(reader, length as usize)
}

/// At most `MAX_TEXT_BYTES`, cut at a character boundary.
fn shortened(text: &str) -> &str {
    let mut end = text.len().min(MAX_TEXT_BYTES as usize);
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    &text[..end]
}

fn invalid(detail: String) -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        format!("display pipe: {detail}"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region() -> Region {
        Region {
            full_width: 8000,
            full_height: 6000,
            x: 3100,
            y: 2300,
            width: 1800,
            height: 1400,
        }
    }

    #[test]
    fn a_request_reads_back_with_and_without_its_svg() {
        for svg in [
            Some("<svg xmlns=\"http://www.w3.org/2000/svg\"/>".to_owned()),
            None,
        ] {
            let request = Request {
                digest: [7; 32],
                region: region(),
                svg,
            };
            let mut bytes = Vec::new();
            write_request(&mut bytes, &request).unwrap();
            let mut reader = bytes.as_slice();
            assert_eq!(read_request(&mut reader).unwrap(), Some(request));
            assert_eq!(
                read_request(&mut reader).unwrap(),
                None,
                "a closed pipe ends the requests"
            );
        }
    }

    #[test]
    fn each_response_reads_back() {
        for response in [
            Response::Image {
                width: 2,
                height: 3,
                stride: 8,
                pixels: (0..24).collect(),
            },
            Response::Failure {
                code: "gpu_insert".to_owned(),
                message: "描けませんでした".to_owned(),
            },
            Response::SceneMissing,
        ] {
            let mut bytes = Vec::new();
            write_response(&mut bytes, &response).unwrap();
            assert_eq!(read_response(&mut bytes.as_slice()).unwrap(), response);
        }
    }

    #[test]
    fn a_pipe_cut_inside_a_request_is_an_error_not_the_end() {
        let mut bytes = Vec::new();
        write_request(
            &mut bytes,
            &Request {
                digest: [1; 32],
                region: region(),
                svg: None,
            },
        )
        .unwrap();
        bytes.truncate(20);
        assert!(read_request(&mut bytes.as_slice()).is_err());
    }

    #[test]
    fn an_image_whose_size_disagrees_is_refused() {
        let mut bytes = Vec::new();
        write_response(
            &mut bytes,
            &Response::Image {
                width: 2,
                height: 3,
                stride: 8,
                pixels: vec![0; 23],
            },
        )
        .unwrap();
        assert!(read_response(&mut bytes.as_slice()).is_err());
    }

    #[test]
    fn a_long_failure_message_is_cut_at_a_character() {
        let message = "あ".repeat(30_000);
        let mut bytes = Vec::new();
        write_response(
            &mut bytes,
            &Response::Failure {
                code: "gpu_read".to_owned(),
                message,
            },
        )
        .unwrap();
        let Response::Failure { message, .. } = read_response(&mut bytes.as_slice()).unwrap()
        else {
            panic!("not a failure");
        };
        assert!(message.len() <= MAX_TEXT_BYTES as usize && message.chars().all(|c| c == 'あ'));
    }
}
