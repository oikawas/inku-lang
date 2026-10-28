//! Bounded, in-memory reading of the ZIP members used by plugin packages.

use flate2::read::DeflateDecoder;
use std::io::{Cursor, Read};

const MAX_MEMBERS: usize = 256;

#[derive(Debug)]
pub(crate) enum ZipError {
    Invalid(String),
    TooManyMembers,
}

#[derive(Debug)]
pub(crate) struct Member {
    pub name: String,
    raw_name: Vec<u8>,
    flags: u16,
    method: u16,
    crc: u32,
    compressed_size: usize,
    uncompressed_size: usize,
    offset: usize,
}

fn u16_at(bytes: &[u8], at: usize) -> Option<u16> {
    Some(u16::from_le_bytes(
        bytes.get(at..at.checked_add(2)?)?.try_into().ok()?,
    ))
}

fn u32_at(bytes: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(
        bytes.get(at..at.checked_add(4)?)?.try_into().ok()?,
    ))
}

fn invalid() -> ZipError {
    ZipError::Invalid(String::new())
}

pub(crate) fn members(data: &[u8]) -> Result<Vec<Member>, ZipError> {
    let start = data.len().saturating_sub(22 + u16::MAX as usize);
    let eocd = (start..data.len().saturating_sub(21))
        .rev()
        .find(|&i| {
            data.get(i..i + 4) == Some(b"PK\x05\x06")
                && u16_at(data, i + 20).is_some_and(|n| i + 22 + n as usize == data.len())
        })
        .ok_or_else(invalid)?;
    let disk = u16_at(data, eocd + 4).ok_or_else(invalid)?;
    let central_disk = u16_at(data, eocd + 6).ok_or_else(invalid)?;
    let on_disk = u16_at(data, eocd + 8).ok_or_else(invalid)?;
    let count = u16_at(data, eocd + 10).ok_or_else(invalid)?;
    let size = u32_at(data, eocd + 12).ok_or_else(invalid)?;
    let offset = u32_at(data, eocd + 16).ok_or_else(invalid)?;
    if disk != 0
        || central_disk != 0
        || on_disk != count
        || count == u16::MAX
        || size == u32::MAX
        || offset == u32::MAX
    {
        return Err(invalid());
    }
    if count as usize > MAX_MEMBERS {
        return Err(ZipError::TooManyMembers);
    }
    let end = (offset as usize)
        .checked_add(size as usize)
        .ok_or_else(invalid)?;
    if end > eocd {
        return Err(invalid());
    }
    let mut cursor = offset as usize;
    let mut result = Vec::with_capacity(count as usize);
    for _ in 0..count {
        if data.get(cursor..cursor + 4) != Some(b"PK\x01\x02") {
            return Err(invalid());
        }
        let name_len = u16_at(data, cursor + 28).ok_or_else(invalid)? as usize;
        let extra_len = u16_at(data, cursor + 30).ok_or_else(invalid)? as usize;
        let comment_len = u16_at(data, cursor + 32).ok_or_else(invalid)? as usize;
        let next = cursor
            .checked_add(46)
            .and_then(|x| x.checked_add(name_len))
            .and_then(|x| x.checked_add(extra_len))
            .and_then(|x| x.checked_add(comment_len))
            .ok_or_else(invalid)?;
        if next > end {
            return Err(invalid());
        }
        let raw_name = data
            .get(cursor + 46..cursor + 46 + name_len)
            .ok_or_else(invalid)?;
        let flags = u16_at(data, cursor + 8).ok_or_else(invalid)?;
        let name = if flags & (1 << 11) != 0 {
            std::str::from_utf8(raw_name)
                .map_err(|_| invalid())?
                .to_owned()
        } else {
            const CP437: &str = "ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■ ";
            let table: Vec<char> = CP437.chars().collect();
            raw_name
                .iter()
                .map(|b| {
                    if *b < 128 {
                        char::from(*b)
                    } else {
                        table[usize::from(*b - 128)]
                    }
                })
                .collect()
        };
        let compressed = u32_at(data, cursor + 20).ok_or_else(invalid)?;
        let uncompressed = u32_at(data, cursor + 24).ok_or_else(invalid)?;
        let local = u32_at(data, cursor + 42).ok_or_else(invalid)?;
        if compressed == u32::MAX
            || uncompressed == u32::MAX
            || local == u32::MAX
            || u16_at(data, cursor + 34) != Some(0)
        {
            return Err(invalid());
        }
        result.push(Member {
            name,
            raw_name: raw_name.to_vec(),
            flags,
            method: u16_at(data, cursor + 10).ok_or_else(invalid)?,
            crc: u32_at(data, cursor + 16).ok_or_else(invalid)?,
            compressed_size: compressed as usize,
            uncompressed_size: uncompressed as usize,
            offset: local as usize,
        });
        cursor = next;
    }
    if cursor != end {
        return Err(invalid());
    }
    Ok(result)
}

fn crc32(data: &[u8]) -> u32 {
    let mut crc = !0u32;
    for byte in data {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb8_8320 & 0u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}

/// Returns None when the expanded member exceeds the caller's bound.
pub(crate) fn read(
    data: &[u8],
    member: &Member,
    limit: usize,
) -> Result<Option<Vec<u8>>, ZipError> {
    let fail = || ZipError::Invalid(member.name.clone());
    let p = member.offset;
    if data.get(p..p.saturating_add(4)) != Some(b"PK\x03\x04")
        || member.flags & 1 != 0
        || !matches!(member.method, 0 | 8)
        || u16_at(data, p + 8) != Some(member.method)
        || u16_at(data, p + 6) != Some(member.flags)
    {
        return Err(fail());
    }
    let name_len = u16_at(data, p + 26).ok_or_else(fail)? as usize;
    let extra_len = u16_at(data, p + 28).ok_or_else(fail)? as usize;
    let start = p
        .checked_add(30)
        .and_then(|x| x.checked_add(name_len))
        .and_then(|x| x.checked_add(extra_len))
        .ok_or_else(fail)?;
    if data.get(p + 30..p + 30 + name_len) != Some(member.raw_name.as_slice()) {
        return Err(fail());
    }
    let end = start.checked_add(member.compressed_size).ok_or_else(fail)?;
    let compressed = data.get(start..end).ok_or_else(fail)?;
    let reader: Box<dyn Read> = if member.method == 0 {
        Box::new(Cursor::new(compressed))
    } else {
        Box::new(DeflateDecoder::new(compressed))
    };
    let mut bytes = Vec::new();
    reader
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| fail())?;
    if bytes.len() > limit {
        return Ok(None);
    }
    if bytes.len() != member.uncompressed_size || crc32(&bytes) != member.crc {
        return Err(fail());
    }
    Ok(Some(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stored_zip(name: &str, contents: &[u8], method: u16) -> Vec<u8> {
        let mut out = Vec::new();
        let u16bytes = |v: u16| v.to_le_bytes();
        let u32bytes = |v: u32| v.to_le_bytes();
        out.extend_from_slice(b"PK\x03\x04");
        out.extend_from_slice(&u16bytes(20));
        out.extend_from_slice(&u16bytes(0));
        out.extend_from_slice(&u16bytes(method));
        out.extend_from_slice(&[0; 4]);
        out.extend_from_slice(&u32bytes(crc32(contents)));
        out.extend_from_slice(&u32bytes(contents.len() as u32));
        out.extend_from_slice(&u32bytes(contents.len() as u32));
        out.extend_from_slice(&u16bytes(name.len() as u16));
        out.extend_from_slice(&u16bytes(0));
        out.extend_from_slice(name.as_bytes());
        out.extend_from_slice(contents);
        let central = out.len() as u32;
        out.extend_from_slice(b"PK\x01\x02");
        out.extend_from_slice(&u16bytes(20));
        out.extend_from_slice(&u16bytes(20));
        out.extend_from_slice(&u16bytes(0));
        out.extend_from_slice(&u16bytes(method));
        out.extend_from_slice(&[0; 4]);
        out.extend_from_slice(&u32bytes(crc32(contents)));
        out.extend_from_slice(&u32bytes(contents.len() as u32));
        out.extend_from_slice(&u32bytes(contents.len() as u32));
        out.extend_from_slice(&u16bytes(name.len() as u16));
        out.extend_from_slice(&[0; 12]);
        out.extend_from_slice(&u32bytes(0));
        out.extend_from_slice(name.as_bytes());
        let central_size = out.len() as u32 - central;
        out.extend_from_slice(b"PK\x05\x06");
        out.extend_from_slice(&[0; 4]);
        out.extend_from_slice(&u16bytes(1));
        out.extend_from_slice(&u16bytes(1));
        out.extend_from_slice(&u32bytes(central_size));
        out.extend_from_slice(&u32bytes(central));
        out.extend_from_slice(&u16bytes(0));
        out
    }

    #[test]
    fn stored_data_checks_crc_and_refuses_unsupported_methods() {
        let zip = stored_zip("package.json", b"{}", 0);
        let member = members(&zip).unwrap().remove(0);
        assert_eq!(read(&zip, &member, 2).unwrap().unwrap(), b"{}");
        assert!(read(&zip, &member, 1).unwrap().is_none());
        let mut corrupt = zip.clone();
        corrupt[30 + "package.json".len()] ^= 1;
        assert!(
            matches!(read(&corrupt, &member, 2), Err(ZipError::Invalid(name)) if name == "package.json")
        );
        let zip = stored_zip("package.json", b"{}", 12);
        let member = members(&zip).unwrap().remove(0);
        assert!(
            matches!(read(&zip, &member, 2), Err(ZipError::Invalid(name)) if name == "package.json")
        );
    }

    #[test]
    fn duplicate_names_preserve_directory_order() {
        let a = stored_zip("same.png", b"first", 0);
        let b = stored_zip("same.png", b"second", 0);
        let ae = a.len() - 22;
        let be = b.len() - 22;
        let ac = u32_at(&a, ae + 16).unwrap() as usize;
        let bc = u32_at(&b, be + 16).unwrap() as usize;
        let mut both = a[..ac].to_vec();
        both.extend_from_slice(&b[..bc]);
        let central_offset = both.len() as u32;
        both.extend_from_slice(&a[ac..ae]);
        let second_central = both.len();
        both.extend_from_slice(&b[bc..be]);
        both[second_central + 42..second_central + 46].copy_from_slice(&(ac as u32).to_le_bytes());
        let size = both.len() as u32 - central_offset;
        both.extend_from_slice(b"PK\x05\x06");
        both.extend_from_slice(&[0; 4]);
        both.extend_from_slice(&2u16.to_le_bytes());
        both.extend_from_slice(&2u16.to_le_bytes());
        both.extend_from_slice(&size.to_le_bytes());
        both.extend_from_slice(&central_offset.to_le_bytes());
        both.extend_from_slice(&0u16.to_le_bytes());
        let entries = members(&both).unwrap();
        assert_eq!(
            entries.iter().map(|m| m.name.as_str()).collect::<Vec<_>>(),
            ["same.png", "same.png"]
        );
        assert_eq!(read(&both, &entries[0], 16).unwrap().unwrap(), b"first");
        assert_eq!(read(&both, &entries[1], 16).unwrap().unwrap(), b"second");
    }

    #[test]
    fn reads_package_and_bounds_expanded_members() {
        let zip = include_bytes!("../../../../docs/plugins/sky-nihonga.zip");
        let entries = members(zip).expect("valid archive");
        let package = entries
            .iter()
            .find(|entry| entry.name == "package.json")
            .unwrap();
        let bytes = read(zip, package, 1_000_000).unwrap().unwrap();
        assert!(
            std::str::from_utf8(&bytes)
                .unwrap()
                .contains("inku.plugin-package.v1")
        );
        assert!(read(zip, package, 1).unwrap().is_none());
        assert!(matches!(members(b"not a zip"), Err(ZipError::Invalid(_))));
    }
}
