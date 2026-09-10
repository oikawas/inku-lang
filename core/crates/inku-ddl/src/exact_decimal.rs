//! Lossless canonical base-10 decimals for explicit DDL geometry.

use std::fmt;

/// A normalized signed base-10 coefficient and scale.
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub struct ExactDecimal {
    coefficient: i128,
    scale: u32,
}

impl ExactDecimal {
    /// Parse one complete decimal spelling without exponent or unit syntax.
    pub fn parse(spelling: &str) -> Result<Self, ExactDecimalError> {
        let bytes = spelling.as_bytes();
        if bytes.is_empty() {
            return Err(ExactDecimalError::InvalidSyntax);
        }
        let (negative, digits) = match bytes[0] {
            b'-' => (true, &bytes[1..]),
            b'+' => (false, &bytes[1..]),
            _ => (false, bytes),
        };
        if digits.is_empty() {
            return Err(ExactDecimalError::InvalidSyntax);
        }
        let mut coefficient = 0_i128;
        let mut scale = 0_u32;
        let mut saw_digit = false;
        let mut saw_dot = false;
        let mut fractional_digit = false;
        for byte in digits {
            match byte {
                b'0'..=b'9' => {
                    saw_digit = true;
                    if saw_dot {
                        fractional_digit = true;
                        scale = scale
                            .checked_add(1)
                            .ok_or(ExactDecimalError::RepresentationLimit)?;
                    }
                    coefficient = coefficient
                        .checked_mul(10)
                        .and_then(|value| value.checked_add(i128::from(byte - b'0')))
                        .ok_or(ExactDecimalError::RepresentationLimit)?;
                }
                b'.' if !saw_dot => saw_dot = true,
                _ => return Err(ExactDecimalError::InvalidSyntax),
            }
        }
        if !saw_digit || (saw_dot && !fractional_digit) {
            return Err(ExactDecimalError::InvalidSyntax);
        }
        if negative {
            coefficient = coefficient
                .checked_neg()
                .ok_or(ExactDecimalError::RepresentationLimit)?;
        }
        Ok(Self::normalized(coefficient, scale))
    }

    /// Construct an exact non-negative integer value.
    pub const fn from_u64(value: u64) -> Self {
        Self {
            coefficient: value as i128,
            scale: 0,
        }
    }

    const fn normalized(mut coefficient: i128, mut scale: u32) -> Self {
        if coefficient == 0 {
            return Self {
                coefficient: 0,
                scale: 0,
            };
        }
        while scale > 0 && coefficient % 10 == 0 {
            coefficient /= 10;
            scale -= 1;
        }
        Self { coefficient, scale }
    }

    pub const fn coefficient(self) -> i128 {
        self.coefficient
    }

    /// The unique non-exponent spelling used by exact macro literals.
    pub fn canonical_spelling(self) -> String {
        let negative = self.coefficient < 0;
        let mut digits = self.coefficient.unsigned_abs().to_string();
        if self.scale > 0 {
            let scale = self.scale as usize;
            if digits.len() <= scale {
                digits = format!("{}{}", "0".repeat(scale + 1 - digits.len()), digits);
            }
            digits.insert(digits.len() - scale, '.');
        }
        if negative {
            format!("-{digits}")
        } else {
            digits
        }
    }

    pub const fn scale(self) -> u32 {
        self.scale
    }

    pub const fn is_positive(self) -> bool {
        self.coefficient > 0
    }

    pub fn is_unit_interval(self) -> Result<bool, ExactDecimalError> {
        let denominator = checked_power_of_ten(self.scale)?;
        Ok(0 <= self.coefficient && self.coefficient <= denominator)
    }

    /// Convert at the one final Score boundary.
    pub fn to_f64(self) -> Result<f64, ExactDecimalError> {
        let denominator = checked_power_of_ten(self.scale)?;
        let value = self.coefficient as f64 / denominator as f64;
        value
            .is_finite()
            .then_some(value)
            .ok_or(ExactDecimalError::RepresentationLimit)
    }

    pub(crate) fn denominator(self) -> Result<i128, ExactDecimalError> {
        checked_power_of_ten(self.scale)
    }
}

/// Stable exact-decimal failures.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExactDecimalError {
    InvalidSyntax,
    RepresentationLimit,
}

impl ExactDecimalError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidSyntax => "invalid_exact_decimal",
            Self::RepresentationLimit => "exact_decimal_representation_limit",
        }
    }
}

impl fmt::Display for ExactDecimalError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for ExactDecimalError {}

pub(crate) fn checked_power_of_ten(scale: u32) -> Result<i128, ExactDecimalError> {
    10_i128
        .checked_pow(scale)
        .ok_or(ExactDecimalError::RepresentationLimit)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn equivalent_spellings_share_one_canonical_value() {
        for spelling in ["0.50", "+0.500", "00.5"] {
            assert_eq!(
                ExactDecimal::parse(spelling).unwrap(),
                ExactDecimal::parse("0.5").unwrap()
            );
        }
        assert_eq!(
            ExactDecimal::parse("-0.0").unwrap(),
            ExactDecimal::from_u64(0)
        );
    }

    #[test]
    fn syntax_and_representation_fail_separately() {
        assert_eq!(
            ExactDecimal::parse("1."),
            Err(ExactDecimalError::InvalidSyntax)
        );
        assert_eq!(
            ExactDecimal::parse("999999999999999999999999999999999999999"),
            Err(ExactDecimalError::RepresentationLimit)
        );
    }
}
