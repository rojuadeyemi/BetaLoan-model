

GAMBLING_PATTERN = (
    r'\b(?:'
    # --- operators / brands (longest first) ---
    r'bet\s*9ja(?:\.com)?|bet\s*king|bet\s*way|bet\s*winner|bet\s*pawa|'
    r'bet\s*bonanza|bet\s*ano|bet\s*jara|bet\s*camp|bet\s*n\s*laff|'
    r'bet\s*wgb|bet\s*24|naira\s*bet|1\s*x\s*bet|22\s*bet|'
    r'sporty(?:\s*bet)?|m\s*sport(?:\s*bet)?|yanga\s*sport|'
    r'gorilla\s*bet\s*365|favour\s*bet\s*365|waddi\s*bet|jolly\s*bet|'
    r'soka\s*bet|bang\s*bet|forte\s*bet|trada\s*bets?|street\s*bet|'
    r'moja\s*bet|cloud\s*bet|live\s*score\s*bet|ze\s*bet|ng\s*bet|'
    r'play\s*naija|play\s*9ja|pari\s*pesa|interwetten|winsapa|'
    r'football\.com|win\s*africa|euro\s*match|n1\s*casino|lot\s*win|'
    r'i\s*lot|'
    r'sports?\s*book(?:ing)?|book(?:maker|ie)|punter|'
    r'gambl(?:e|ing|er)|casino|accumulator|acca|'
    r'wager(?:ing|s)?|jackpot|lotto|lottery|cash\s*out|'
    r'virtual\s*(?:sports?|bet)|odds|stake|'
    r'bet(?:ting|s)?'
    r')\b'
)



# ---------------------------------------------------------------- lenders
LENDERS = (
    r'fair\s*money\s*(?:loan|zero|app)|ren\s*money\s*(?:loan|zero|app)|\baella\b|quickcheck|quick\s*check|'
    r'palm\s*credit\s*(?:loan|zero|app)|palmpay\s*(?:loan|flexi)|easy\s*buy|new\s*credit|new\s*edge|'
    r'kwik\s*cash|kwik\s*money|soko\s*loan|go\s*cash|ease\s*moni|\bokash\b|blue\s*ridge|'
    r'\bxcredit\b|x\s*credit|creditville|credit\s*ville|\bspecta\b|credit\s*direct|'
    r'pay\s*hippo|lendigo|\bumba\b|cash\s*bus|9\s*credit|bless\s*me\s*loan|kia\s*kia|'
    r'\blapo\b|\bmigo\b|\bcredpal\b|zedvance\s*(?:loan|zero|app)|altara|\blidya\b|\bfint\b|'
    r'\bkredi\b|trade\s*lenda|rosabon|evolve\s*credit|salad\s*africa|fundall|'
    r'loan\s*spot|naira\s*loan|naija\s*loan|carbon\s*(?:loan|zero|app)|pay\s*later|'
    r'accion \s*(?:loan|zero|app)|baobab|fina\s*trust\s*(?:loan|zero|app)|ab\s*micro\s*finance\s*(?:loan|zero|app)'
)

PRODUCTS = (
    r'quick\s*credit|quick\s*bucks|quick\s*loan|first\s*advance|first\s*credit|'
    r'click\s*credit|cash\s*lite|ready\s*cash|soft\s*loan|easy\s*cash|ez\s*cash|'
    r'fast\s*loan|xpress\s*loan|express\s*loan|salary\s*advance|cash\s*advance|'
    r'\bpayday\b|personal\s*loan|consumer\s*loan|instant\s*loan|emergency\s*loan|'
    r'micro\s*loan|term\s*loan|staff\s*loan|employee\s*loan|cooperative\s*(?:loan|deduction)|'
    r'union\s*loan|credit\s*facility|\boverdraft\b|\bod\s*repayment\b'
)

# ------------------------------------------------- repayment / servicing terms
REPAYMENT = (
    r'\brepay(?:ment|ments|ing|ed|s)?\b|\brepmt\b|\brpymt\b|\brepymt\b|'
    r'loan\s*(?:deduction|settlement|recovery|servicing|liquidation|collection|'
    r'top\s*up|refinanc\w*|arrears?)|'
    r'debt\s*servicing|principal\s*(?:repayment|payment)?|interest\s*(?:repayment|charge)|'
    r'(?:monthly|weekly|daily|scheduled|auto|automatic)\s*(?:repayment|deduction|debit)|'
    r'\binstal{1,2}ments?\b|\bemi\b|\bamorti[sz]ation\b|\barrears\b|\bmoratorium\b|'
    r'\btenor\b|outstanding\s*balance|late\s*(?:fee|payment|charge)|penalty\s*charge|'
    r'roll\s*over|part\s*payment|full\s*settlement'
)

# ------------------------------------------- debit mandates / recovery rails
MANDATES = (
    r'standing\s*order|\bgsi\b|global\s*standing\s*instruction|'
    r'e\s*-?\s*mandate|debit\s*mandate|\bremita\b|auto\s*debit|auto\s*deduct\w*'
)

# ---------------------------------------------------------------- BNPL / cards
BNPL = (
    r'buy\s*now\s*pay\s*later|\bbnpl\b|deferred\s*payment|pay\s*in\s*4|'
    r'credit\s*card\s*(?:payment|repayment)|card\s*repayment|minimum\s*payment'
)

# --------------------------------------------------- generic catch-all (last)
GENERIC = r'\bloans?\b|\blending\b|\blender\b|\bcredit\s*(?:repayment|deduction)\b'

REPAYMENT_PATTERN = (
    r'\b(?:' + '|'.join([LENDERS, PRODUCTS, REPAYMENT, MANDATES, BNPL, GENERIC]) + r')\b'
)


DISBURSEMENT = (
    r'disburse(?:ment|ments|d|s)?|disbursal|\bdisb\b|\bdsb\b|loan\s*disb\w*|'
    r'facility\s*disburs\w*|principal\s*disburs\w*|loan\s*proceeds?|'
    r'draw\s*down|drawdown|loan\s*draw\w*|credit\s*line\s*draw\w*|'
    r'loan\s*(?:credit|credited|received|approved|granted|issued|payout|pay\s*out)|'
    r'loan\s*top\s*up\s*disburs\w*|advance\s*(?:received|credited|payout)|'
    r'salary\s*advance\s*(?:credit|disburs\w*)|overdraft\s*draw\w*|'
    r'new\s*loan|loan\s*booking|loan\s*booked|value\s*date\s*loan'
)

BORROWING = (
    r'borrow(?:ed|ing|s)?|\bloan\s*from\b|funds?\s*borrowed|'
    r'credit\s*facility\s*(?:granted|approved|drawn)|'
    r'\bbnpl\s*(?:order|checkout|purchase)|pay\s*in\s*4\s*(?:order|purchase)'
)

LOAN_RECEIVED    = r'\b(?:' + '|'.join([DISBURSEMENT, BORROWING, LENDERS, PRODUCTS]) + r')\b'


# ---------------------------- STRONG: unambiguous payroll credits
PAYROLL = (
    r'\bsalar(?:y|ies)\b|\bsal\b|\bslry\b|\bsalry\b|\bsals\b|\bsala\b|'
    r'\bpayroll\b|\bpay\s*roll\b|\bwages?\b|\bnet\s*pay\b|\btake\s*home\b|'
    r'\bpay\s*slip\b|\bpayslip\b|\bemolument\w*\b|\bremuneration\b|'
    r'salary\s*(?:payment|credit|upload|run|for|arrears)|'
    r'staff\s*(?:salary|pay|emolument)|monthly\s*(?:salary|pay|emolument)|'
    r'personnel\s*cost|\bback\s*pay\b|\bbackpay\b|'
    r'ZEDVA\s+(?:[A-Z]{3})|[A-Z]{2}\s+A$|\bearnings\b|'
    r'\bnet\s*pay\b'
)



# --------------- Nigerian public-sector payroll rails and salary scales
PUBLIC_SECTOR = (
    r'\bippis\b|\bgifmis\b|\bipps\b|con(?:hess|mess|piss|tiss|puass|raiss)\b|'
    r'consolidated\s*(?:salary|emolument)|'
    r'federal\s*pay\w*|state\s*pay\w*|\bmda\s*salary\b|\bsalar\b'
)

ALLOWANCES = (
    r'(?:13th|thirteenth)\s*month|\ballowance[s]?\b|\bstipend\b|\bhonorarium\b|\bovertime\b|\bot\s*pay\b|'
    r'(?:leave|housing|transport|hazard|shift|sitting|call\s*duty|meal|'
    r'furniture|wardrobe|responsibility|duty|utility)\s*allowance|'
    r'\bbonus\b|(?:performance|productivity|year\s*end|festive)\s*bonus|'
    r'\bnysc\b|nysc\s*allow\w*|\ballowee\b|\bsiwes\b|\bitf\s*allow\w*|'
    r'\bgratuity\b|\bseverance\b|terminal\s*benefit|\bpension\b|\bretirement\s*benefit\b|CLPB'
)

# ------------------------------ month-tagged salary refs: SAL/JAN/2026, SAL-MAR26
MONTH_TAGGED = (
    r'\bsal(?:ary)?[\s._/-]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
    r'[a-z]*[\s._/-]*\d{0,4}|'
    r'\bsal(?:ary)?[\s._/-]*\d{1,2}[\s./-]\d{2,4}|' \
    r'\w+ \d+ sa'
)


SALARY_RECEIVED      = r'(?:' + '|'.join([PAYROLL, PUBLIC_SECTOR, MONTH_TAGGED]) + r')'


EXCLUSION = (
    r'\bemtl\b|electronic\s*money\s*transfer\s*levy|transfer\s*levy|'
    r'\b(?:trf|transfer|nip|neft|rtgs|sms|card|atm|pos|account|acct|maintenance|'
    r'mgt|management|alert)\s*(?:charge|charges|fee|fees|levy|comm|commission)\b|'
    r'\bsms\s*alert\b|\bstamp\s*dut(?:y|ies)\b|\bcot\b|commission\s*on|commission\s*\d+|'
    r'\bvat\b|\bahtc\b|account\s*maintenance|card\s*issuance|token\s*fee|'
    r'excise\s*duty|withholding\s*tax|\bwht\b|COMM\s+(?:Alat|NIP|FEE|FEES)'
)

KEYWORDS = (
    r'\btr(?:f|sf|sfr|nsf|ansfer|ansfers|ansferred)\b|\btrfr?\b|\bxfer\b|\btrans\b|Turnover|'
    r'\bfunds?\s*transfer\b|\bft\s*trf\b|\bwire\s*transfer\b|\bswift\b|\btelegraphic\b|'
    r'\b(?:in|out)ward\b|\binw\b|\boutw\b|\bincoming\b|\boutgoing\b|'
    r'\btransfer\s*(?:to|from|frm)\b|\btrf\s*(?:to|from|frm)\b|'
    r'\bsent?\s*(?:to|from)\b|\breceived?\s*from\b|\brcvd\b|\bsender\b|\bbeneficiary\b|'
    r'\bcash\s*(?:deposit|dep|withdrawal|withdraw|wdl|pickup|payment)\b|\bcsh\s*dep\b|'
    r'\bteller\b|\bcounter\s*deposit\b|\blodg?ement\b|pos|From'
    r'\bmerchant\s*settlement\b|\bsettlement\b|\bpayout\b|\bremittance\b|'
    r'\bwestern\s*union\b|\bmoneygram\b|\bworldremit\b|\bsendwave\b|\bremitly\b|\bimto\b|\bNFT\b'
)
 
CHANNELS = (
    r'\bnip\b|\bnibss\b|\bneft\b|\brtgs\b|\bimps\b|\bach\b|\beft\b|\bnxg\b|'
    r'\bgtworld\b|\bhbr\b|\bhyd\b|\bpaystack\b|\bflutterwave\b|\bmonnify\b|'
    r'\binterswitch\b|\bremita\b|\bpaga\b|atm|card|mobile|app|ibank|internet|inet|ussd|trf'
    r'\bussd\b|\*\d{3}\*|\bmobile\s*(?:app|banking|trf)\b|\bib\s*trf\b|\bibank\b'
)
 
STRUCTURAL = (
    r'\bweb\s*:\s*[a-z0-9]{2,10}\s*/|'                      # GTB: web:TB1c/.../NAME
    r'\b(?:mob|mobile|app|ussd|atm|ib|inet|internet|nip|trf)\s*[:/]\s*\w|'
    r'^[^/\n]{0,25}/[^/\n]{1,45}/\s*[A-Za-z]|'              # any purpose/name triple
    r'\*{3,}|'                                              # masked digits
    r'\b\d{10}\b'                                           # NUBAN account no.
)


STOPWORDS = {
    'SUPPLY','PAYMENT','PURCHASE','DEPOSIT','WITHDRAWAL',
    'LTD','LIMITED','NIG','NIGERIA','PLC','ENTERPRISE','ENTERPRISES','VENT','VENTURES',
    'CASH','RENT','FUEL','FOOD','GIFT','SAVINGS','REPAIR','SERVICE','TOTAL','MATERIAL','LAND','MOTOR','VEHICLE','MOBILE','PHONE',
    'BUILDING','CONSTRUCTION','INTERNET','BROADBAND','INSURANCE','HMO','RENOVATION'
    'SCHOOL','UNIVERSITY','COLLEGE','ACADEMY','INSTITUTE','ACADEMY','HOSPITAL','CLINIC','PHARMACY','MEDICAL','HEALTHCARE',
    'TRAVEL','TOURISM','HOTEL','RESORT','RESTAURANT','BAR','LOUNGE','CAFE','RECREATION','ENTERTAINMENT',
    'FITNESS','GYM','STADIUM','ARENA','PARK','PLAYGROUND','PARKING','GARAGE','STORAGE','WAREHOUSE','SAND','GRAVEL','CEMENT','STEEL','TIMBER','WOOD','PLASTIC','GLASS','CERAMIC','TEXTILE','FABRIC',
    'MEAL','GROCERY','SUPERMARKET','MARKET','SHOP','STORE','MALL','PLAZA','BOUTIQUE','SALON','SPA','BARBER','BEAUTY','COSMETIC',
    'FARM','AGRICULTURE','FISHERY','FORESTRY','MINING','OIL','GAS','ENERGY','POWER','ELECTRIC','SOLAR','WIND','NUCLEAR',
    'TECHNOLOGY','SOFTWARE','HARDWARE','ELECTRONICS','COMPUTER','INFORMATION','COMMUNICATION','MEDIA','ADVERTISING','MARKETING','BRANDING','PUBLICITY',
    'FINANCE','BANKING','INVESTMENT','INSURANCE','ACCOUNTING','AUDITING','LEGAL','LAW','CONSULTING','MANAGEMENT','HUMAN','RESOURCES','RECRUITMENT',
    'TRANSPORT','LOGISTICS','SHIPPING','DELIVERY','COURIER','FREIGHT','WAREHOUSING','DISTRIBUTION','CHAIN','MANUFACTURING','INDUSTRY','FACTORY','PLANT','PRODUCTION',
    'RESEARCH','DEVELOPMENT','EDUCATION','TRAINING','TEACHING','LEARNING','COACHING','MENTORING','SUPERVISION','ASSESSMENT','EVALUATION','CERTIFICATION','ACCREDITATION',
    'GOVERNMENT','PUBLIC','SECTOR','PRIVATE','NONPROFIT','NGO','CHARITY','FOUNDATION','ASSOCIATION','ORGANIZATION','INSTITUTION','SOCIETY','CLUB','COMMUNITY','GROUP','NETWORK','FUND'
}

STOPWORDS_PATTERN = r'(?:' + '|'.join(STOPWORDS) + r')'
 
TRANSFER_PATTERN = r'(?:' + '|'.join([KEYWORDS, CHANNELS, STRUCTURAL,STOPWORDS_PATTERN]) + r')'
