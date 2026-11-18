// Centralized translations (English / हिन्दी / తెలుగు). One dictionary, one t(). Changing language only changes
// presentation - never the model, its labels, probabilities or the prediction (those come from the server unchanged).
export const LANGS = { en: "English", hi: "हिन्दी", te: "తెలుగు" };
let lang = (typeof localStorage !== "undefined" && localStorage.getItem("auracry_lang")) || "en";
if (!LANGS[lang]) lang = "en";
const subs = new Set();

export const getLang = () => lang;
export function setLang(l) {
  if (!LANGS[l] || l === lang) return;
  lang = l;
  try { localStorage.setItem("auracry_lang", l); } catch { /* ignore */ }
  if (typeof document !== "undefined") { document.documentElement.lang = l; document.body?.setAttribute("data-lang", l); }
  subs.forEach((fn) => fn(l));
}
export const onLangChange = (fn) => subs.add(fn);

export function t(key, params) {
  const row = D[key];
  let s = (row && (row[lang] ?? row.en)) ?? key;
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

// The five cry classes. Model output is unchanged; only the shown name is localized.
const CLASS = {
  Hungry: { en: "Hungry", hi: "भूखा", te: "ఆకలి" },
  Tired: { en: "Tired", hi: "थका हुआ", te: "అలసట" },
  Discomfort: { en: "Discomfort", hi: "बेचैनी", te: "అసౌకర్యం" },
  "Belly Pain": { en: "Belly Pain", hi: "पेट दर्द", te: "పొట్ట నొప్పి" },
  "Needs Burping": { en: "Needs Burping", hi: "डकार चाहिए", te: "త్రేన్పు కావాలి" },
  Unclear: { en: "Unclear", hi: "अस्पष्ट", te: "అస్పష్టం" },
  // legacy labels that may still appear in old saved analyses
  Scared: { en: "Scared", hi: "डरा हुआ", te: "భయం" }, "Cold / Hot": { en: "Cold / Hot", hi: "ठंड / गर्मी", te: "చలి / వేడి" },
  Lonely: { en: "Lonely", hi: "अकेला", te: "ఒంటరితనం" },
};
export const tClass = (label) => (CLASS[label] ? (CLASS[label][lang] ?? CLASS[label].en) : label);

// Backend sends an `error` code with every failure; translate by code, fall back to the server's own message.
export const tErr = (code, serverMessage, params) => (D["err_" + code] ? t("err_" + code, params) : (serverMessage || t("err_generic")));

const D = {
  // language picker
  language: { en: "Language", hi: "भाषा", te: "భాష" },

  // nav / layout
  nav_home: { en: "Home", hi: "होम", te: "హోమ్" },
  nav_history: { en: "History", hi: "इतिहास", te: "చరిత్ర" },
  nav_lab: { en: "Lab", hi: "लैब", te: "ల్యాబ్" },
  nav_profile: { en: "Profile", hi: "प्रोफ़ाइल", te: "ప్రొఫైల్" },
  admin_console: { en: "Administrator console", hi: "व्यवस्थापक कंसोल", te: "అడ్మినిస్ట్రేటర్ కన్సోల్" },
  logout: { en: "Logout", hi: "लॉग आउट", te: "లాగ్ అవుట్" },

  // common
  loading: { en: "Loading", hi: "लोड हो रहा है", te: "లోడ్ అవుతోంది" },
  back: { en: "Back", hi: "वापस", te: "వెనుకకు" },
  save: { en: "Save", hi: "सहेजें", te: "సేవ్ చేయి" },
  tagline: { en: "Understand your baby's cry", hi: "अपने शिशु के रोने को समझें", te: "మీ శిశువు ఏడుపును అర్థం చేసుకోండి" },

  // ---- auth ----
  sign_in: { en: "SIGN IN", hi: "साइन इन", te: "సైన్ ఇన్" },
  login_as: { en: "Login as", hi: "इस रूप में लॉगिन करें", te: "ఇలా లాగిన్ అవ్వండి" },
  role_user: { en: "User", hi: "उपयोगकर्ता", te: "వినియోగదారు" },
  role_admin: { en: "Admin", hi: "व्यवस्थापक", te: "అడ్మిన్" },
  f_email_user: { en: "Email / Username", hi: "ईमेल / उपयोगकर्ता नाम", te: "ఇమెయిల్ / వినియోగదారు పేరు" },
  btn_continue: { en: "CONTINUE", hi: "आगे बढ़ें", te: "కొనసాగించు" },
  checking: { en: "Checking...", hi: "जाँच हो रही है...", te: "తనిఖీ చేస్తోంది..." },
  new_user: { en: "New user?", hi: "नए उपयोगकर्ता?", te: "కొత్త వినియోగదారా?" },
  register: { en: "Register", hi: "रजिस्टर करें", te: "నమోదు చేయండి" },
  forgot_password: { en: "Forgot password?", hi: "पासवर्ड भूल गए?", te: "పాస్‌వర్డ్ మర్చిపోయారా?" },
  step_label: { en: "STEP {n} OF {t} · {label}", hi: "चरण {n} / {t} · {label}", te: "దశ {n} / {t} · {label}" },
  s_password: { en: "Password", hi: "पासवर्ड", te: "పాస్‌వర్డ్" },
  s_email_code: { en: "Email code", hi: "ईमेल कोड", te: "ఇమెయిల్ కోడ్" },
  s_security_pin: { en: "Security PIN", hi: "सुरक्षा पिन", te: "భద్రతా పిన్" },
  f_password: { en: "Password", hi: "पासवर्ड", te: "పాస్‌వర్డ్" },
  welcome_back_name: { en: "Welcome back, ", hi: "फिर से स्वागत है, ", te: "తిరిగి స్వాగతం, " },
  btn_sign_in: { en: "SIGN IN", hi: "साइन इन करें", te: "సైన్ ఇన్ చేయి" },
  verifying: { en: "Verifying...", hi: "सत्यापन हो रहा है...", te: "ధృవీకరిస్తోంది..." },
  use_diff_account: { en: "← Use a different account", hi: "← किसी अन्य खाते का उपयोग करें", te: "← వేరే ఖాతాను ఉపయోగించండి" },
  btn_verify_code: { en: "VERIFY CODE", hi: "कोड सत्यापित करें", te: "కోడ్ ధృవీకరించు" },
  code_sent_to: { en: "We sent a code to ", hi: "हमने एक कोड भेजा है ", te: "మేము కోడ్‌ను పంపాము " },
  code_expires: { en: ". It expires in a few minutes.", hi: "। यह कुछ मिनटों में समाप्त हो जाएगा।", te: ". ఇది కొన్ని నిమిషాల్లో గడువు ముగుస్తుంది." },
  your_email: { en: "your email", hi: "आपका ईमेल", te: "మీ ఇమెయిల్" },
  resend_code: { en: "Resend code", hi: "कोड पुनः भेजें", te: "కోడ్‌ను మళ్లీ పంపు" },
  resend_in: { en: "Resend code in {s}s", hi: "{s} सेकंड में कोड पुनः भेजें", te: "{s}సె లో కోడ్ మళ్లీ పంపు" },
  new_code_sent: { en: "A new code was sent.", hi: "एक नया कोड भेजा गया।", te: "కొత్త కోడ్ పంపబడింది." },
  create_pin: { en: "Create a 4-6 digit PIN", hi: "4-6 अंकों का पिन बनाएँ", te: "4-6 అంకెల పిన్ సృష్టించండి" },
  confirm_pin: { en: "Confirm PIN", hi: "पिन की पुष्टि करें", te: "పిన్ నిర్ధారించండి" },
  btn_set_pin_sign_in: { en: "SET PIN & SIGN IN", hi: "पिन सेट करें और साइन इन करें", te: "పిన్ సెట్ చేసి సైన్ ఇన్ అవ్వండి" },
  pin_setup_note: { en: "One-time setup: choose a PIN you'll enter each time you sign in.", hi: "एक बार की सेटअप: एक पिन चुनें जिसे आप हर बार साइन इन करते समय दर्ज करेंगे।", te: "ఒకసారి సెటప్: ప్రతిసారి సైన్ ఇన్ అయ్యేటప్పుడు నమోదు చేసే పిన్‌ను ఎంచుకోండి." },
  pin_enter_finish: { en: "Enter your security PIN to finish signing in.", hi: "साइन इन पूरा करने के लिए अपना सुरक्षा पिन दर्ज करें।", te: "సైన్ ఇన్ పూర్తి చేయడానికి మీ భద్రతా పిన్‌ను నమోదు చేయండి." },
  signing_in: { en: "Signing in...", hi: "साइन इन हो रहा है...", te: "సైన్ ఇన్ అవుతోంది..." },

  // reset
  reset_password: { en: "Reset password", hi: "पासवर्ड रीसेट करें", te: "పాస్‌వర్డ్ రీసెట్ చేయండి" },
  btn_send_reset: { en: "SEND RESET CODE", hi: "रीसेट कोड भेजें", te: "రీసెట్ కోడ్ పంపు" },
  reset_blurb: { en: "We'll email you a code to set a new password.", hi: "हम आपको नया पासवर्ड सेट करने के लिए एक कोड ईमेल करेंगे।", te: "కొత్త పాస్‌వర్డ్ సెట్ చేయడానికి మేము మీకు కోడ్‌ను ఇమెయిల్ చేస్తాము." },
  back_to_sign_in: { en: "← Back to sign in", hi: "← साइन इन पर वापस जाएँ", te: "← సైన్ ఇన్‌కు తిరిగి వెళ్ళండి" },
  f_account_email: { en: "Your account email", hi: "आपका खाता ईमेल", te: "మీ ఖాతా ఇమెయిల్" },
  f_reset_code: { en: "Reset code", hi: "रीसेट कोड", te: "రీసెట్ కోడ్" },
  f_new_password: { en: "New password", hi: "नया पासवर्ड", te: "కొత్త పాస్‌వర్డ్" },
  f_confirm_new_password: { en: "Confirm new password", hi: "नया पासवर्ड पुष्टि करें", te: "కొత్త పాస్‌వర్డ్ నిర్ధారించండి" },
  btn_set_new_password: { en: "SET NEW PASSWORD", hi: "नया पासवर्ड सेट करें", te: "కొత్త పాస్‌వర్డ్ సెట్ చేయి" },

  // register
  create_account_sub: { en: "Create your account", hi: "अपना खाता बनाएँ", te: "మీ ఖాతాను సృష్టించండి" },
  btn_create_account: { en: "CREATE ACCOUNT", hi: "खाता बनाएँ", te: "ఖాతా సృష్టించు" },
  f_full_name: { en: "Full name", hi: "पूरा नाम", te: "పూర్తి పేరు" },
  f_email: { en: "Email", hi: "ईमेल", te: "ఇమెయిల్" },
  f_confirm_password: { en: "Confirm password", hi: "पासवर्ड की पुष्टि करें", te: "పాస్‌వర్డ్ నిర్ధారించండి" },
  f_pin: { en: "Security PIN (4-6 digits)", hi: "सुरक्षा पिन (4-6 अंक)", te: "భద్రతా పిన్ (4-6 అంకెలు)" },
  pin_signup_note: { en: "Your security PIN is the third login step (after password and email code).", hi: "आपका सुरक्षा पिन तीसरा लॉगिन चरण है (पासवर्ड और ईमेल कोड के बाद)।", te: "మీ భద్రతా పిన్ మూడవ లాగిన్ దశ (పాస్‌వర్డ్ మరియు ఇమెయిల్ కోడ్ తర్వాత)." },
  already_registered: { en: "Already registered?", hi: "पहले से पंजीकृत?", te: "ఇప్పటికే నమోదు అయ్యారా?" },
  login: { en: "Login", hi: "लॉगिन", te: "లాగిన్" },
  account_created: { en: "Account created! Please sign in.", hi: "खाता बन गया! कृपया साइन इन करें।", te: "ఖాతా సృష్టించబడింది! దయచేసి సైన్ ఇన్ అవ్వండి." },

  // client-side validation
  v_enter_email: { en: "Please enter your email.", hi: "कृपया अपना ईमेल दर्ज करें।", te: "దయచేసి మీ ఇమెయిల్ నమోదు చేయండి." },
  v_enter_password: { en: "Please enter your password.", hi: "कृपया अपना पासवर्ड दर्ज करें।", te: "దయచేసి మీ పాస్‌వర్డ్ నమోదు చేయండి." },
  v_code_digits: { en: "Enter the 6-digit code.", hi: "6 अंकों का कोड दर्ज करें।", te: "6 అంకెల కోడ్ నమోదు చేయండి." },
  v_pin_digits: { en: "PIN must be 4-6 digits.", hi: "पिन 4-6 अंकों का होना चाहिए।", te: "పిన్ 4-6 అంకెలు ఉండాలి." },
  v_pins_no_match: { en: "PINs do not match.", hi: "पिन मेल नहीं खाते।", te: "పిన్‌లు సరిపోలడం లేదు." },
  v_pw_rule: { en: "Password must be at least 8 characters with a letter and a number.", hi: "पासवर्ड कम से कम 8 अक्षरों का होना चाहिए, जिसमें एक अक्षर और एक संख्या हो।", te: "పాస్‌వర్డ్ కనీసం 8 అక్షరాలు, ఒక అక్షరం మరియు ఒక సంఖ్యతో ఉండాలి." },
  v_pw_no_match: { en: "Passwords do not match.", hi: "पासवर्ड मेल नहीं खाते।", te: "పాస్‌వర్డ్‌లు సరిపోలడం లేదు." },
  v_fill_all: { en: "Please fill in every field.", hi: "कृपया हर फ़ील्ड भरें।", te: "దయచేసి ప్రతి ఫీల్డ్ నింపండి." },

  // dev-mode OTP banner
  dev_mode_code: { en: "Dev mode (no email configured): your code is {code}", hi: "डेव मोड (कोई ईमेल कॉन्फ़िगर नहीं): आपका कोड {code} है", te: "డెవ్ మోడ్ (ఇమెయిల్ కాన్ఫిగర్ చేయలేదు): మీ కోడ్ {code}" },

  // backend error codes
  err_invalid_credentials: { en: "Incorrect email or password.", hi: "गलत ईमेल या पासवर्ड।", te: "తప్పు ఇమెయిల్ లేదా పాస్‌వర్డ్." },
  err_access_denied: { en: "Access denied.", hi: "पहुँच अस्वीकृत।", te: "యాక్సెస్ తిరస్కరించబడింది." },
  err_inactive: { en: "This account is deactivated. Please contact the administrator.", hi: "यह खाता निष्क्रिय है। कृपया व्यवस्थापक से संपर्क करें।", te: "ఈ ఖాతా నిష్క్రియం చేయబడింది. దయచేసి అడ్మిన్‌ను సంప్రదించండి." },
  err_locked: { en: "Account temporarily locked. Please try again later.", hi: "खाता अस्थायी रूप से लॉक है। कृपया बाद में पुनः प्रयास करें।", te: "ఖాతా తాత్కాలికంగా లాక్ చేయబడింది. దయచేసి తర్వాత ప్రయత్నించండి." },
  err_otp_invalid: { en: "Incorrect code.", hi: "गलत कोड।", te: "తప్పు కోడ్." },
  err_otp_expired: { en: "The code expired. Please request a new one.", hi: "कोड समाप्त हो गया। कृपया नया अनुरोध करें।", te: "కోడ్ గడువు ముగిసింది. దయచేసి కొత్తది అభ్యర్థించండి." },
  err_otp_locked: { en: "Too many incorrect codes. Please start again.", hi: "बहुत अधिक गलत कोड। कृपया फिर से शुरू करें।", te: "చాలా తప్పు కోడ్‌లు. దయచేసి మళ్లీ ప్రారంభించండి." },
  err_pin_invalid: { en: "Incorrect PIN.", hi: "गलत पिन।", te: "తప్పు పిన్." },
  err_pin_locked: { en: "Too many incorrect PIN tries. Please start again.", hi: "बहुत अधिक गलत पिन प्रयास। कृपया फिर से शुरू करें।", te: "చాలా తప్పు పిన్ ప్రయత్నాలు. దయచేసి మళ్లీ ప్రారంభించండి." },
  err_cooldown: { en: "Please wait before requesting another code.", hi: "कृपया एक और कोड का अनुरोध करने से पहले प्रतीक्षा करें।", te: "మరో కోడ్ అభ్యర్థించే ముందు దయచేసి వేచి ఉండండి." },
  err_expired: { en: "Your session expired. Please start again.", hi: "आपका सत्र समाप्त हो गया। कृपया फिर से शुरू करें।", te: "మీ సెషన్ గడువు ముగిసింది. దయచేసి మళ్లీ ప్రారంభించండి." },
  err_too_many_attempts: { en: "Too many attempts. Please wait a few minutes.", hi: "बहुत अधिक प्रयास। कृपया कुछ मिनट प्रतीक्षा करें।", te: "చాలా ప్రయత్నాలు. దయచేసి కొన్ని నిమిషాలు వేచి ఉండండి." },
  err_csrf: { en: "Security token expired. Please refresh and try again.", hi: "सुरक्षा टोकन समाप्त हो गया। कृपया रीफ़्रेश करके पुनः प्रयास करें।", te: "భద్రతా టోకెన్ గడువు ముగిసింది. దయచేసి రిఫ్రెష్ చేసి ప్రయత్నించండి." },
  err_rate_limited: { en: "Too many requests. Please slow down and try again shortly.", hi: "बहुत अधिक अनुरोध। कृपया धीमे चलें और थोड़ी देर में पुनः प्रयास करें।", te: "చాలా అభ్యర్థనలు. దయచేసి నెమ్మదిగా, కొద్దిసేపటి తర్వాత ప్రయత్నించండి." },
  err_duplicate: { en: "You just submitted this same recording. Please wait a moment.", hi: "आपने अभी यही रिकॉर्डिंग सबमिट की है। कृपया थोड़ा प्रतीक्षा करें।", te: "మీరు ఇప్పుడే ఇదే రికార్డింగ్‌ను సమర్పించారు. దయచేసి కొద్దిసేపు వేచి ఉండండి." },
  err_generic: { en: "Something went wrong. Please try again.", hi: "कुछ गलत हो गया। कृपया पुनः प्रयास करें।", te: "ఏదో తప్పు జరిగింది. దయచేసి మళ్లీ ప్రయత్నించండి." },
  // upload validation (Phase 9)
  err_not_audio: { en: "This file is not a real audio recording. Please upload a WAV, MP3, M4A, OGG or FLAC file.", hi: "यह फ़ाइल वास्तविक ऑडियो रिकॉर्डिंग नहीं है। कृपया WAV, MP3, M4A, OGG या FLAC फ़ाइल अपलोड करें।", te: "ఈ ఫైల్ నిజమైన ఆడియో రికార్డింగ్ కాదు. దయచేసి WAV, MP3, M4A, OGG లేదా FLAC ఫైల్ అప్‌లోడ్ చేయండి." },
  err_has_video: { en: "This looks like a video file. Please upload an audio-only recording.", hi: "यह एक वीडियो फ़ाइल लगती है। कृपया केवल-ऑडियो रिकॉर्डिंग अपलोड करें।", te: "ఇది వీడియో ఫైల్ లా ఉంది. దయచేసి ఆడియో-మాత్రమే రికార్డింగ్ అప్‌లోడ్ చేయండి." },
  err_empty_file: { en: "This file is empty.", hi: "यह फ़ाइल खाली है।", te: "ఈ ఫైల్ ఖాళీగా ఉంది." },
  err_too_large: { en: "File is too large (max 15 MB).", hi: "फ़ाइल बहुत बड़ी है (अधिकतम 15 MB)।", te: "ఫైల్ చాలా పెద్దది (గరిష్ఠం 15 MB)." },
  err_too_short: { en: "Audio is too short. Please provide at least 1 second of crying.", hi: "ऑडियो बहुत छोटा है। कृपया कम से कम 1 सेकंड का रोना दें।", te: "ఆడియో చాలా చిన్నది. దయచేసి కనీసం 1 సెకను ఏడుపు ఇవ్వండి." },
  err_too_long: { en: "Audio is too long (max 60 seconds). Please upload a shorter clip.", hi: "ऑडियो बहुत लंबा है (अधिकतम 60 सेकंड)। कृपया छोटा क्लिप अपलोड करें।", te: "ఆడియో చాలా పొడవుగా ఉంది (గరిష్ఠం 60 సెకన్లు). దయచేసి చిన్న క్లిప్ అప్‌లోడ్ చేయండి." },
  err_unsupported_ext: { en: "Unsupported file type. Use WAV, MP3, M4A, OGG or FLAC.", hi: "असमर्थित फ़ाइल प्रकार। WAV, MP3, M4A, OGG या FLAC का उपयोग करें।", te: "మద్దతు లేని ఫైల్ రకం. WAV, MP3, M4A, OGG లేదా FLAC ఉపయోగించండి." },
  err_invalid_audio: { en: "This audio could not be analysed. Try a clearer recording.", hi: "इस ऑडियो का विश्लेषण नहीं हो सका। स्पष्ट रिकॉर्डिंग आज़माएँ।", te: "ఈ ఆడియోను విశ్లేషించలేకపోయాం. స్పష్టమైన రికార్డింగ్ ప్రయత్నించండి." },
  // quality warnings shown on the result (non-blocking)
  quality_heading: { en: "Recording quality", hi: "रिकॉर्डिंग गुणवत्ता", te: "రికార్డింగ్ నాణ్యత" },
  warn_silent: { en: "The recording is almost silent, so the result is unreliable.", hi: "रिकॉर्डिंग लगभग मौन है, इसलिए परिणाम अविश्वसनीय है।", te: "రికార్డింగ్ దాదాపు నిశ్శబ్దంగా ఉంది, కాబట్టి ఫలితం నమ్మదగినది కాదు." },
  warn_clipped: { en: "The audio is distorted (too loud). Try recording a little further away.", hi: "ऑडियो विकृत है (बहुत तेज़)। थोड़ा दूर से रिकॉर्ड करने का प्रयास करें।", te: "ఆడియో వక్రీకరించబడింది (చాలా బిగ్గరగా). కొంచెం దూరం నుండి రికార్డ్ చేయండి." },
  warn_noisy: { en: "High background noise - the result may be less reliable.", hi: "अधिक पृष्ठभूमि शोर - परिणाम कम विश्वसनीय हो सकता है।", te: "అధిక నేపథ్య శబ్దం - ఫలితం తక్కువ నమ్మదగినదిగా ఉండవచ్చు." },
  warn_maybe_not_cry: { en: "This may not be a newborn cry. The result is unreliable - a valid audio file is not proof of a cry.", hi: "यह नवजात शिशु का रोना नहीं हो सकता। परिणाम अविश्वसनीय है - एक वैध ऑडियो फ़ाइल रोने का प्रमाण नहीं है।", te: "ఇది నవజాత శిశువు ఏడుపు కాకపోవచ్చు. ఫలితం నమ్మదగినది కాదు - చెల్లుబాటు అయ్యే ఆడియో ఫైల్ ఏడుపుకు రుజువు కాదు." },

  // ---- home ----
  welcome_back: { en: "Welcome back,", hi: "फिर से स्वागत है,", te: "తిరిగి స్వాగతం," },
  understand_every: { en: "Understand every ", hi: "हर ", te: "ప్రతి " },
  cry_word: { en: "cry", hi: "रोना समझें", te: "ఏడుపును అర్థం చేసుకోండి" },
  home_blurb: { en: "Record or upload your baby's cry. Two models - a feature-based classifier and a deep neural network - analyse it together and suggest what to try.", hi: "अपने शिशु का रोना रिकॉर्ड या अपलोड करें। दो मॉडल - एक फ़ीचर-आधारित क्लासिफ़ायर और एक डीप न्यूरल नेटवर्क - मिलकर इसका विश्लेषण करते हैं और सुझाव देते हैं।", te: "మీ శిశువు ఏడుపును రికార్డ్ చేయండి లేదా అప్‌లోడ్ చేయండి. రెండు మోడల్‌లు - ఫీచర్ ఆధారిత క్లాసిఫైయర్ మరియు డీప్ న్యూరల్ నెట్‌వర్క్ - కలిసి విశ్లేషించి సూచనలు ఇస్తాయి." },
  start_analysis: { en: "Start Cry Analysis", hi: "रोना विश्लेषण शुरू करें", te: "ఏడుపు విశ్లేషణ ప్రారంభించండి" },
  see_models: { en: "🔬 See how the models work (Pipeline Lab)", hi: "🔬 देखें मॉडल कैसे काम करते हैं (पाइपलाइन लैब)", te: "🔬 మోడల్‌లు ఎలా పనిచేస్తాయో చూడండి (పైప్‌లైన్ ల్యాబ్)" },
  model_unavailable: { en: "The model is not available yet, so analysis is temporarily disabled.", hi: "मॉडल अभी उपलब्ध नहीं है, इसलिए विश्लेषण अस्थायी रूप से अक्षम है।", te: "మోడల్ ఇంకా అందుబాటులో లేదు, కాబట్టి విశ్లేషణ తాత్కాలికంగా నిలిపివేయబడింది." },
  analyses_performed: { en: "Analyses performed", hi: "किए गए विश्लेषण", te: "చేసిన విశ్లేషణలు" },
  recent_analyses: { en: "Recent analyses", hi: "हाल के विश्लेषण", te: "ఇటీవలి విశ్లేషణలు" },
  see_all: { en: "See all", hi: "सभी देखें", te: "అన్నీ చూడండి" },
  no_analyses_cta: { en: "No analyses yet. Tap “Start Cry Analysis” to begin.", hi: "अभी तक कोई विश्लेषण नहीं। शुरू करने के लिए “रोना विश्लेषण शुरू करें” पर टैप करें।", te: "ఇంకా విశ్లేషణలు లేవు. ప్రారంభించడానికి “ఏడుపు విశ్లేషణ ప్రారంభించండి”ని నొక్కండి." },
  unclear_x: { en: "Unclear ({x})", hi: "अस्पष्ट ({x})", te: "అస్పష్టం ({x})" },

  // ---- choose / record / ready / processing ----
  choose_audio: { en: "Choose audio", hi: "ऑडियो चुनें", te: "ఆడియో ఎంచుకోండి" },
  upload_audio: { en: "Upload Audio", hi: "ऑडियो अपलोड करें", te: "ఆడియో అప్‌లోడ్ చేయండి" },
  upload_formats: { en: "WAV, MP3, M4A, OGG or FLAC (max 15 MB)", hi: "WAV, MP3, M4A, OGG या FLAC (अधिकतम 15 MB)", te: "WAV, MP3, M4A, OGG లేదా FLAC (గరిష్ఠం 15 MB)" },
  record_cry: { en: "Record Cry", hi: "रोना रिकॉर्ड करें", te: "ఏడుపు రికార్డ్ చేయండి" },
  use_mic: { en: "Use your microphone", hi: "अपने माइक्रोफ़ोन का उपयोग करें", te: "మీ మైక్రోఫోన్ ఉపయోగించండి" },
  tip_record: { en: "Tip: record 5-10 seconds, 20-30 cm from the baby, in a quiet room.", hi: "सुझाव: शांत कमरे में, शिशु से 20-30 सेमी दूर, 5-10 सेकंड रिकॉर्ड करें।", te: "చిట్కా: నిశ్శబ్ద గదిలో, శిశువు నుండి 20-30 సెం.మీ దూరంలో, 5-10 సెకన్లు రికార్డ్ చేయండి." },
  v_unsupported: { en: "Unsupported file type. Please choose a WAV, MP3, M4A, OGG or FLAC file.", hi: "असमर्थित फ़ाइल प्रकार। कृपया WAV, MP3, M4A, OGG या FLAC फ़ाइल चुनें।", te: "మద్దతు లేని ఫైల్ రకం. దయచేసి WAV, MP3, M4A, OGG లేదా FLAC ఫైల్ ఎంచుకోండి." },
  v_empty: { en: "This file is empty.", hi: "यह फ़ाइल खाली है।", te: "ఈ ఫైల్ ఖాళీగా ఉంది." },
  v_too_large: { en: "File is too large. The limit is 15 MB.", hi: "फ़ाइल बहुत बड़ी है। सीमा 15 MB है।", te: "ఫైల్ చాలా పెద్దది. పరిమితి 15 MB." },
  record_title: { en: "Record cry", hi: "रोना रिकॉर्ड करें", te: "ఏడుపు రికార్డ్ చేయండి" },
  tap_start_stop: { en: "Tap to start, tap again to stop", hi: "शुरू करने के लिए टैप करें, रोकने के लिए फिर टैप करें", te: "ప్రారంభించడానికి నొక్కండి, ఆపడానికి మళ్లీ నొక్కండి" },
  use_recording: { en: "Use This Recording", hi: "इस रिकॉर्डिंग का उपयोग करें", te: "ఈ రికార్డింగ్‌ను ఉపయోగించండి" },
  v_rec_https: { en: "Recording needs https:// or localhost. You can upload a file instead.", hi: "रिकॉर्डिंग के लिए https:// या localhost चाहिए। आप इसके बजाय फ़ाइल अपलोड कर सकते हैं।", te: "రికార్డింగ్‌కు https:// లేదా localhost అవసరం. బదులుగా ఫైల్ అప్‌లోడ్ చేయవచ్చు." },
  v_mic_blocked: { en: "Microphone access was blocked. Allow it in the browser, or upload a file.", hi: "माइक्रोफ़ोन एक्सेस अवरुद्ध था। इसे ब्राउज़र में अनुमति दें, या फ़ाइल अपलोड करें।", te: "మైక్రోఫోన్ యాక్సెస్ బ్లాక్ చేయబడింది. బ్రౌజర్‌లో అనుమతించండి లేదా ఫైల్ అప్‌లోడ్ చేయండి." },
  v_rec_read: { en: "Could not read the recording. Please try again.", hi: "रिकॉर्डिंग पढ़ी नहीं जा सकी। कृपया पुनः प्रयास करें।", te: "రికార్డింగ్‌ను చదవలేకపోయింది. దయచేసి మళ్లీ ప్రయత్నించండి." },
  v_too_short: { en: "That was too short. Record at least 2 seconds.", hi: "यह बहुत छोटा था। कम से कम 2 सेकंड रिकॉर्ड करें।", te: "అది చాలా చిన్నది. కనీసం 2 సెకన్లు రికార్డ్ చేయండి." },
  audio_ready: { en: "Audio ready", hi: "ऑडियो तैयार", te: "ఆడియో సిద్ధం" },
  recorded: { en: "Recorded", hi: "रिकॉर्ड किया गया", te: "రికార్డ్ చేయబడింది" },
  uploaded: { en: "Uploaded", hi: "अपलोड किया गया", te: "అప్‌లోడ్ చేయబడింది" },
  duration_s: { en: "Duration {s} s", hi: "अवधि {s} से", te: "వ్యవధి {s} సె" },
  duration_unknown: { en: "Duration unknown", hi: "अवधि अज्ञात", te: "వ్యవధి తెలియదు" },
  get_results: { en: "GET RESULTS", hi: "परिणाम प्राप्त करें", te: "ఫలితాలు పొందండి" },
  choose_another: { en: "Choose another audio", hi: "दूसरा ऑडियो चुनें", te: "మరో ఆడియో ఎంచుకోండి" },
  analyzing: { en: "Analyzing Cry...", hi: "रोने का विश्लेषण हो रहा है...", te: "ఏడుపు విశ్లేషిస్తోంది..." },
  running_pipeline: { en: "The server is running the real pipeline now.", hi: "सर्वर अभी वास्तविक पाइपलाइन चला रहा है।", te: "సర్వర్ ఇప్పుడు నిజమైన పైప్‌లైన్‌ను అమలు చేస్తోంది." },
  replaying_steps: { en: "Replaying what the server measured, step by step:", hi: "सर्वर ने जो मापा, उसे चरण दर चरण दिखाया जा रहा है:", te: "సర్వర్ కొలిచినదాన్ని దశలవారీగా చూపుతోంది:" },
  uploading_waiting: { en: "Uploading and analysing (waiting for the server)", hi: "अपलोड और विश्लेषण (सर्वर की प्रतीक्षा)", te: "అప్‌లోడ్ మరియు విశ్లేషణ (సర్వర్ కోసం వేచి ఉంది)" },
  analysis_failed: { en: "Analysis failed", hi: "विश्लेषण विफल", te: "విశ్లేషణ విఫలమైంది" },

  // ---- result ----
  result_title: { en: "Result", hi: "परिणाम", te: "ఫలితం" },
  analysis_details: { en: "Analysis details", hi: "विश्लेषण विवरण", te: "విశ్లేషణ వివరాలు" },
  predicted_category: { en: "Predicted category", hi: "अनुमानित श्रेणी", te: "అంచనా వర్గం" },
  best_guess: { en: "Best guess: {x}", hi: "सर्वोत्तम अनुमान: {x}", te: "ఉత్తమ అంచనా: {x}" },
  confidence: { en: "Confidence", hi: "विश्वास", te: "విశ్వాసం" },
  all_categories: { en: "All categories", hi: "सभी श्रेणियाँ", te: "అన్ని వర్గాలు" },
  why_answer: { en: "Why this answer", hi: "यह उत्तर क्यों", te: "ఈ సమాధానం ఎందుకు" },
  deep_model_title: { en: "Deep model (CNN + BiGRU)", hi: "डीप मॉडल (CNN + BiGRU)", te: "డీప్ మోడల్ (CNN + BiGRU)" },
  deep_model_blurb: { en: "Second opinion from the neural network on the spectrogram.", hi: "स्पेक्ट्रोग्राम पर न्यूरल नेटवर्क की दूसरी राय।", te: "స్పెక్ట్రోగ్రామ్‌పై న్యూరల్ నెట్‌వర్క్ రెండవ అభిప్రాయం." },
  how_decided: { en: "How the models decided", hi: "मॉडल ने कैसे निर्णय लिया", te: "మోడల్‌లు ఎలా నిర్ణయించాయి" },
  what_try: { en: "What you can try", hi: "आप क्या आज़मा सकते हैं", te: "మీరు ఏమి ప్రయత్నించవచ్చు" },
  when_help: { en: "When to get medical help", hi: "चिकित्सा सहायता कब लें", te: "వైద్య సహాయం ఎప్పుడు తీసుకోవాలి" },
  audio: { en: "Audio", hi: "ऑडियो", te: "ఆడియో" },
  mel_spec: { en: "Mel spectrogram", hi: "मेल स्पेक्ट्रोग्राम", te: "మెల్ స్పెక్ట్రోగ్రామ్" },
  quality_label: { en: "Recording quality", hi: "रिकॉर्डिंग गुणवत्ता", te: "రికార్డింగ్ నాణ్యత" },
  q_good: { en: "Good", hi: "अच्छी", te: "మంచిది" },
  q_fair: { en: "Fair", hi: "ठीक-ठाक", te: "ఓ మోస్తరు" },
  q_poor: { en: "Poor", hi: "खराब", te: "బలహీనం" },
  q_snr: { en: "Signal-to-noise: {db} dB", hi: "सिग्नल-टू-नॉइज़: {db} dB", te: "సిగ్నల్-టు-నాయిస్: {db} dB" },
  audio_original: { en: "Original", hi: "मूल", te: "అసలు" },
  audio_cleaned: { en: "Noise-reduced", hi: "शोर-रहित", te: "శబ్దం తగ్గించినది" },
  cleaned_hint: { en: "Noise reduction is for listening only - the models analyse the original audio.", hi: "शोर-कमी केवल सुनने के लिए है - मॉडल मूल ऑडियो का विश्लेषण करते हैं।", te: "శబ్ద తగ్గింపు వినడానికి మాత్రమే - మోడల్‌లు అసలు ఆడియోను విశ్లేషిస్తాయి." },
  uncertain_note: { en: "The model is not sure (runner-up: {x}). Treat this as a guess and use the checklist below.", hi: "मॉडल निश्चित नहीं है (दूसरा विकल्प: {x})। इसे एक अनुमान मानें और नीचे दी गई सूची का उपयोग करें।", te: "మోడల్‌కు ఖచ్చితంగా తెలియదు (రెండవది: {x}). దీన్ని అంచనాగా భావించి క్రింది జాబితాను ఉపయోగించండి." },
  experimental_note: { en: "AuraCry is an experimental study project, not a medical device.", hi: "AuraCry एक प्रायोगिक अध्ययन परियोजना है, कोई चिकित्सा उपकरण नहीं।", te: "AuraCry ఒక ప్రయోగాత్మక అధ్యయన ప్రాజెక్ట్, వైద్య పరికరం కాదు." },
  download_report: { en: "Download PDF report", hi: "PDF रिपोर्ट डाउनलोड करें", te: "PDF నివేదికను డౌన్‌లోడ్ చేయండి" },
  medical_disclaimer_title: { en: "Important", hi: "महत्वपूर्ण", te: "ముఖ్యమైనది" },
  medical_disclaimer: { en: "This result is experimental and may be wrong. A high confidence score is not medical certainty. AuraCry does not diagnose and does not replace a pediatrician. If your baby seems unwell or you are worried, contact a doctor.", hi: "यह परिणाम प्रायोगिक है और गलत हो सकता है। उच्च विश्वास स्कोर चिकित्सीय निश्चितता नहीं है। AuraCry निदान नहीं करता और बाल रोग विशेषज्ञ का विकल्प नहीं है। यदि आपका शिशु अस्वस्थ लगे या आप चिंतित हों, तो डॉक्टर से संपर्क करें।", te: "ఈ ఫలితం ప్రయోగాత్మకమైనది, తప్పు కావచ్చు. అధిక విశ్వాస స్కోరు వైద్య నిశ్చయత కాదు. AuraCry రోగ నిర్ధారణ చేయదు, పిల్లల వైద్యునికి ప్రత్యామ్నాయం కాదు. మీ శిశువు అनారోగ్యంగా అనిపిస్తే లేదా మీరు ఆందోళన చెందితే, వైద్యుడిని సంప్రదించండి." },

  // ---- profile ----
  profile_title: { en: "Profile", hi: "प्रोफ़ाइल", te: "ప్రొఫైల్" },
  edit_profile: { en: "Edit profile", hi: "प्रोफ़ाइल संपादित करें", te: "ప్రొఫైల్ సవరించండి" },
  f_name: { en: "Name", hi: "नाम", te: "పేరు" },
  profile_updated: { en: "Profile updated.", hi: "प्रोफ़ाइल अपडेट हो गई।", te: "ప్రొఫైల్ నవీకరించబడింది." },
  change_password: { en: "Change password", hi: "पासवर्ड बदलें", te: "పాస్‌వర్డ్ మార్చండి" },
  f_current_password: { en: "Current password", hi: "वर्तमान पासवर्ड", te: "ప్రస్తుత పాస్‌వర్డ్" },
  f_confirm_new: { en: "Confirm new password", hi: "नया पासवर्ड पुष्टि करें", te: "కొత్త పాస్‌వర్డ్ నిర్ధారించండి" },
  password_changed: { en: "Password changed.", hi: "पासवर्ड बदल गया।", te: "పాస్‌వర్డ్ మార్చబడింది." },
};
