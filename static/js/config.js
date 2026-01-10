/**
 * Frontend Configuration
 * Centralized configuration for the frontend application
 */

export const config = {
  // API configuration
  apiBaseUrl: '/api',

  // Polling intervals (milliseconds)
  downloadStatusPollInterval: 5000, // 5 seconds

  // UI refresh intervals (milliseconds)
  libraryRefreshInterval: 30000, // 30 seconds

  // Cache busting version
  assetsVersion: Date.now().toString(),
};

/**
 * Centralized language and country mappings
 */

// Language code to full name mapping
export const languageMap = {
  'en': 'English',
  'de': 'German',
  'fr': 'French',
  'es': 'Spanish',
  'it': 'Italian',
  'ja': 'Japanese',
  'pt': 'Portuguese',
  'ru': 'Russian',
  'zh': 'Chinese',
  'ko': 'Korean',
  'nl': 'Dutch',
  'pl': 'Polish',
  'tr': 'Turkish',
  'ar': 'Arabic',
  'hi': 'Hindi',
  'sv': 'Swedish',
  'no': 'Norwegian',
  'da': 'Danish',
  'fi': 'Finnish',
  'uk': 'Ukrainian',
  'cs': 'Czech',
  'el': 'Greek',
  'he': 'Hebrew',
  'th': 'Thai',
  'vi': 'Vietnamese',
  'id': 'Indonesian',
  'ms': 'Malay',
  'ro': 'Romanian',
  'hu': 'Hungarian',
  'bg': 'Bulgarian',
  'hr': 'Croatian',
  'sk': 'Slovak',
  'sl': 'Slovenian',
  'sr': 'Serbian',
  'lt': 'Lithuanian',
  'lv': 'Latvian',
  'et': 'Estonian'
};

// Country code to full name mapping
export const countryMap = {
  'US': 'United States',
  'UK': 'United Kingdom',
  'DE': 'Germany',
  'FR': 'France',
  'ES': 'Spain',
  'IT': 'Italy',
  'JP': 'Japan',
  'CA': 'Canada',
  'AU': 'Australia',
  'BR': 'Brazil',
  'MX': 'Mexico',
  'NL': 'Netherlands',
  'SE': 'Sweden',
  'NO': 'Norway',
  'DK': 'Denmark',
  'FI': 'Finland',
  'PL': 'Poland',
  'RU': 'Russia',
  'CN': 'China',
  'KR': 'South Korea',
  'IN': 'India',
  'AR': 'Argentina',
  'CL': 'Chile',
  'CO': 'Colombia',
  'PE': 'Peru',
  'VE': 'Venezuela',
  'PT': 'Portugal',
  'BE': 'Belgium',
  'AT': 'Austria',
  'CH': 'Switzerland',
  'GR': 'Greece',
  'TR': 'Turkey',
  'ZA': 'South Africa',
  'NZ': 'New Zealand',
  'IE': 'Ireland',
  'CZ': 'Czech Republic',
  'HU': 'Hungary',
  'RO': 'Romania',
  'BG': 'Bulgaria',
  'HR': 'Croatia',
  'SK': 'Slovakia',
  'SI': 'Slovenia',
  'RS': 'Serbia',
  'LT': 'Lithuania',
  'LV': 'Latvia',
  'EE': 'Estonia',
  'UA': 'Ukraine',
  'IL': 'Israel',
  'TH': 'Thailand',
  'VN': 'Vietnam',
  'ID': 'Indonesia',
  'MY': 'Malaysia',
  'SG': 'Singapore',
  'PH': 'Philippines'
};

// Country indicators for detecting country from text
export const countryIndicators = {
  'UK': ['[UK]', ' UK ', '.UK.', 'British'],
  'US': ['[US]', ' US ', '.US.', 'American'],
  'DE': ['[DE]', ' DE ', '.DE.', 'German', 'Deutschland'],
  'FR': ['[FR]', ' FR ', '.FR.', 'French', 'France'],
  'ES': ['[ES]', ' ES ', '.ES.', 'Spain', 'Spanish'],
  'IT': ['[IT]', ' IT ', '.IT.', 'Italy', 'Italian'],
  'JP': ['[JP]', ' JP ', '.JP.', 'Japan', 'Japanese'],
  'CA': ['[CA]', ' CA ', '.CA.', 'Canada', 'Canadian'],
  'AU': ['[AU]', ' AU ', '.AU.', 'Australia', 'Australian'],
  'NL': ['[NL]', ' NL ', '.NL.', 'Netherlands', 'Dutch'],
  'BR': ['[BR]', ' BR ', '.BR.', 'Brazil', 'Brazilian'],
  'MX': ['[MX]', ' MX ', '.MX.', 'Mexico', 'Mexican'],
  'SE': ['[SE]', ' SE ', '.SE.', 'Sweden', 'Swedish'],
  'NO': ['[NO]', ' NO ', '.NO.', 'Norway', 'Norwegian'],
  'DK': ['[DK]', ' DK ', '.DK.', 'Denmark', 'Danish'],
  'FI': ['[FI]', ' FI ', '.FI.', 'Finland', 'Finnish'],
  'PL': ['[PL]', ' PL ', '.PL.', 'Poland', 'Polish'],
  'RU': ['[RU]', ' RU ', '.RU.', 'Russia', 'Russian'],
  'CN': ['[CN]', ' CN ', '.CN.', 'China', 'Chinese'],
  'KR': ['[KR]', ' KR ', '.KR.', 'Korea', 'Korean'],
  'UA': ['[UA]', ' UA ', '.UA.', 'Ukraine', 'Ukrainian'],
  'PT': ['[PT]', ' PT ', '.PT.', 'Portugal', 'Portuguese'],
  'GR': ['[GR]', ' GR ', '.GR.', 'Greece', 'Greek'],
  'TR': ['[TR]', ' TR ', '.TR.', 'Turkey', 'Turkish'],
  'CZ': ['[CZ]', ' CZ ', '.CZ.', 'Czech'],
  'IN': ['[IN]', ' IN ', '.IN.', 'India', 'Indian']
};

// Language indicators for detecting language from text
export const languageIndicators = {
  'en': ['English', '[EN]', ' EN ', '.EN.'],
  'de': ['German', 'Deutsch', '[DE]', ' DE ', '.DE.'],
  'fr': ['French', 'Français', '[FR]', ' FR ', '.FR.'],
  'es': ['Spanish', 'Español', '[ES]', ' ES ', '.ES.'],
  'it': ['Italian', 'Italiano', '[IT]', ' IT ', '.IT.'],
  'ja': ['Japanese', '[JP]', ' JP ', '.JP.'],
  'pt': ['Portuguese', 'Português', '[PT]', ' PT ', '.PT.'],
  'ru': ['Russian', 'Русский', '[RU]', ' RU ', '.RU.'],
  'zh': ['Chinese', '中文', '[CN]', ' CN ', '.CN.'],
  'nl': ['Dutch', 'Nederlands', '[NL]', ' NL ', '.NL.'],
  'pl': ['Polish', 'Polski', '[PL]', ' PL ', '.PL.'],
  'uk': ['Ukrainian', 'Українська', '[UA]', ' UA ', '.UA.'],
  'sv': ['Swedish', 'Svenska', '[SE]', ' SE ', '.SE.'],
  'no': ['Norwegian', 'Norsk', '[NO]', ' NO ', '.NO.'],
  'da': ['Danish', 'Dansk', '[DK]', ' DK ', '.DK.'],
  'fi': ['Finnish', 'Suomi', '[FI]', ' FI ', '.FI.'],
  'ko': ['Korean', '[KR]', ' KR ', '.KR.'],
  'tr': ['Turkish', 'Türkçe', '[TR]', ' TR ', '.TR.'],
  'cs': ['Czech', 'Čeština', '[CZ]', ' CZ ', '.CZ.'],
  'el': ['Greek', 'Ελληνικά', '[GR]', ' GR ', '.GR.']
};

// Language to country mapping (most common associations)
export const languageToCountry = {
  'en': 'US',
  'de': 'DE',
  'fr': 'FR',
  'es': 'ES',
  'it': 'IT',
  'ja': 'JP',
  'pt': 'PT',
  'ru': 'RU',
  'zh': 'CN',
  'ko': 'KR',
  'nl': 'NL',
  'pl': 'PL',
  'tr': 'TR',
  'ar': 'SA',
  'hi': 'IN',
  'sv': 'SE',
  'no': 'NO',
  'da': 'DK',
  'fi': 'FI',
  'uk': 'UA',
  'cs': 'CZ',
  'el': 'GR',
  'he': 'IL',
  'th': 'TH',
  'vi': 'VN',
  'id': 'ID',
  'ms': 'MY'
};

// Category IDs for Newsnab providers
export const categoryIds = {
  'all_books': 7000,
  'ebooks': 7020,
  'magazines': 7010,
  'comics': 7030
};
