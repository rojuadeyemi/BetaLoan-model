"""Bank statement data extraction and transformation."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, Generic, TypeVar, Pattern
from enum import Enum
from personal.pattern import GAMBLING_PATTERN, REPAYMENT_PATTERN,LOAN_RECEIVED, SALARY_RECEIVED, ALLOWANCES,EXCLUSION,TRANSFER_PATTERN
T = TypeVar('T')

def _import_pandas():
    """Lazy import pandas to defer ~40-50MB allocation until first use."""
    import pandas as pd
    return pd


def _import_numpy():
    """Lazy import numpy."""
    import numpy as np
    return np

class StatementType(Enum):
    """Supported bank statement formats."""
    MBS = "mbs"
    MONO = "mono"
    GENERIC = "generic"

class BaseStatementProcessor(ABC, Generic[T]):
    """
    Abstract base class for statement processors.
    Implements Template Method pattern for extensibility.
    """

    def __init__(self, data: T,current_balance: float = None):
        self.data = data
        pd = _import_pandas()
        self.df = pd.DataFrame()
        self.current_balance = current_balance

    @abstractmethod
    def validate_data_format(self) -> bool:
        """Validate if data format is supported."""
        pass

    @abstractmethod
    def extract_transactions(self) -> pd.DataFrame:
        """Extract transactions from data."""
        pass

    @abstractmethod
    def normalize_fields(self) -> None:
        """Normalize field names to standard format."""
        pass

    def enrich_dates(self) -> None:
        """Add temporal enrichment (month-year, week number)."""
        pd = _import_pandas()
        if 'date' not in self.df.columns:
            raise Exception('date field not found in the dataframe')

        self.df['date'] = pd.to_datetime(self.df['date'], errors='coerce').dt.tz_localize(None)
        self.df['monthyear'] = self.df['date'].dt.strftime('%Y-%m')
        iso = self.df['date'].dt.isocalendar()
        self.df['weekno'] = iso.year * 100 + iso.week
    
    def apply_date_cutoff(self, months=6):
        """Filter transactions to last N months."""
        if 'date' in self.df.columns:
            from dateutil.relativedelta import relativedelta
            cutoff = self.df['date'].max() - relativedelta(months=months)
            self.df = self.df[self.df['date'] >= cutoff]

    def reconstruct_balance(self):
            """Reconstruct balance from current_balance working backwards if balance is null."""
            if 'balance' not in self.df.columns or self.current_balance is None:
                return
            if self.df['balance'].notna().any():
                return

            np = _import_numpy()
            # Transactions should be oldest-first; work backwards from the end
            amounts = self.df['amount'].fillna(0).values.copy()
            types = self.df['type'].values
            balances = np.empty(len(amounts))

            bal = self.current_balance
            for i in range(len(amounts) - 1, -1, -1):
                balances[i] = bal
                if types[i] == 'credit':
                    bal -= amounts[i]
                else:
                    bal += abs(amounts[i])

            self.df['balance'] = balances

    def process(self) -> pd.DataFrame:
        if not self.validate_data_format():
            raise ValueError("Invalid data format")

        self.df = self.extract_transactions()
        if self.df.empty:
            return self.df

        self.normalize_fields()
        self.reconstruct_balance()
        self.enrich_dates()
        self.apply_date_cutoff()

        return self.df

class MBSProcessor(BaseStatementProcessor[Dict[str, Any]]):
    """MBS (Moniepoint Business Statement) Statement Processor."""

    FIELD_MAP = {
        'PTransactionDate': 'date',
        'PCredit': 'credit',
        'PDebit': 'debit',
        'PNarration': 'narration',
        'PBalance': 'balance'
    }
    
    def validate_data_format(self) -> bool:
        return isinstance(self.data, dict) and 'TicketNo' in self.data

    def extract_transactions(self) -> pd.DataFrame:
        try:
            pd = _import_pandas()
            if isinstance(self.data['Details'], str):
                parsed_data = json.loads(self.data['Details'])
                return pd.DataFrame(parsed_data).iloc[1:]
            elif isinstance(self.data['Details'], list):
                return pd.DataFrame(self.data['Details']).iloc[1:]
            else:
                raise ValueError(f"Unexpected data format for MBS data: {self.data['Details']}")
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Error parsing MBS data: {e}")

    def normalize_fields(self):
        if self.df.empty:
            return
        
        np = _import_numpy()
        self.df.rename(columns=self.FIELD_MAP, inplace=True)
        numeric_cols = ['credit', 'debit', 'balance'] 
        self.df[numeric_cols] = self.df[numeric_cols].astype(float, copy=False)
        self.df['amount'] = self.df['credit'].fillna(0) + self.df['debit'].fillna(0)
        self.df['type'] = np.where(self.df['credit'] > 0, 'credit', 'debit')

class MonoProcessor(BaseStatementProcessor[Dict[str, Any]]):
    """Mono Bank Statement Processor."""
    
    FIELD_MAP = {
        'Date': 'date',
        'Type': 'type',
        'Amount': 'amount',
        'Category': 'category',
        'Narration': 'narration',
        'Balance': 'balance'
    }
    
    def validate_data_format(self) -> bool:
        return isinstance(self.data, dict) and 'data' in self.data

    def extract_transactions(self) -> pd.DataFrame:
        try:
            pd = _import_pandas()
            data_list = self.data.get('data', [])
            if not data_list:
                return pd.DataFrame()
            return pd.DataFrame(data_list)
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Error parsing Mono data: {e}")

    def normalize_fields(self):
        if self.df.empty:
            return
        
        self.df.rename(columns=self.FIELD_MAP, inplace=True)

        if 'amount' in self.df.columns:
            self.df['amount'] = self.df['amount'] / 100

        if 'balance' in self.df.columns:
            self.df['balance'] = self.df['balance'] / 100

        # Reverse Mono to match oldest to newest chronology
        self.df = self.df.iloc[::-1].reset_index(drop=True)

class GenericProcessor(BaseStatementProcessor[Dict[str, Any]]):
    """
    Generic processor for new statement providers.
    Configurable field mapping for extensibility.
    """

    def __init__(self, data: Dict[str, Any], field_mapping: Optional[Dict[str, str]] = None, current_balance: float = None):
        super().__init__(data,current_balance=current_balance)
        self.field_mapping = field_mapping or self._get_default_mapping()

    def _get_default_mapping(self) -> Dict[str, str]:
        """Default field mapping for generic processor."""
        return {
            'transaction_date': 'date',
            'description': 'narration',
            'amount': 'amount',
            'balance': 'balance',
            'transaction_type': 'type'
        }

    def validate_data_format(self) -> bool:
        return isinstance(self.data, dict) and (
            'transaction_date' in self.data or 
            'data' in self.data or
            'transactions' in self.data or
            'records' in self.data
        )

    def extract_transactions(self) -> pd.DataFrame:
        try:
            pd = _import_pandas()
            transaction_data = (
                self.data.get('transactions') or
                self.data.get('data') or
                self.data.get('records', [])
            )

            if isinstance(transaction_data, str):
                transaction_data = json.loads(transaction_data)

            return pd.DataFrame(transaction_data)

        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Error parsing generic data: {e}")

    def normalize_fields(self) -> None:
        if self.df.empty:
            return

        pd = _import_pandas()
        np = _import_numpy()

        # Handle camelCase to snake_case conversion for common fields
        camelcase_mapping = {
            'transactionDate': 'transaction_date',
            'creditAmount': 'credit',
            'debitAmount': 'debit',
        }
        
        # Apply camelCase conversion first
        for camel, snake in camelcase_mapping.items():
            if camel in self.df.columns:
                self.df.rename(columns={camel: snake}, inplace=True)
        
        # Apply configured field mapping
        self.df.rename(columns=self.field_mapping, inplace=True)
        
        # Handle credit/debit format (common in many banks)
        if 'credit' in self.df.columns and 'debit' in self.df.columns:
            self.df['credit'] = pd.to_numeric(self.df['credit'], errors='coerce').fillna(0)
            self.df['debit'] = pd.to_numeric(self.df['debit'], errors='coerce').fillna(0)
            self.df['amount'] = self.df['credit'] + self.df['debit']
            self.df['type'] = np.where(self.df['credit'] > 0, 'credit', 'debit')
        
        # Handle single amount with type field
        elif 'amount' in self.df.columns:
            self.df['amount'] = pd.to_numeric(self.df['amount'], errors='coerce').fillna(0)
            
            # Derive type if not present
            if 'type' not in self.df.columns:
                # Assume positive is credit, negative is debit
                self.df['type'] = np.where(self.df['amount'] > 0, 'credit', 'debit')
                self.df['amount'] = self.df['amount'].abs()
        
        # Ensure balance is numeric
        if 'balance' in self.df.columns:
            self.df['balance'] = pd.to_numeric(self.df['balance'], errors='coerce')

class BaseDataTransformer:
    """Base class for common data transformation methods."""
    
    # Define rules with raw patterns
    _CATEGORY_PATTERNS = [
            ('reversal', r'revers|rvsl|REV-|RETURNED|refund|REV:|REVERSAL|REV\s+'),
            ('VAS', r'Startimes|gotv|dstv|electricity|cable|airtime|\bmtn\b|airtel|\bglo\b|9mobile|VTU|Voucher|Internet bundle|Recharge card|recharge|Night plan|Data|USSD TOPUP'),
            ('loan_repayment', REPAYMENT_PATTERN),
            ('loan_credit', LOAN_RECEIVED),
            ('bonus/allowance', ALLOWANCES),
            ('salary',SALARY_RECEIVED),
            ('betting', GAMBLING_PATTERN),
            ('drift', r'Contribution'),
            ('travelling', r'Embassy|flight|VISA|VFS Global|TLS Contact|IRCC|USCIS|Express Entry|Airfare|One-way ticket|IELTS|TOEFL|WES fee|CAS deposit|SEVIS fee|Proof of Funds|GIC Payment|Form A'),
            ('transfer', TRANSFER_PATTERN),
            ('others', r'.*')  # Catch-all for uncategorized transactions
                    ]
    
    _EXCLUSION_PATTERN = EXCLUSION
    
    # Pre-compiled regex patterns cached at class level (40-50% performance improvement)
    _compiled_patterns: Dict[str, Pattern] = {}
    _exclusion_compiled: Optional[Pattern] = None
    
    @classmethod
    def _get_compiled_patterns(cls) -> Dict[str, Pattern]:
        """Get or compile regex patterns (lazy compilation on first use)."""
        if not cls._compiled_patterns:
            cls._compiled_patterns = {
                category: re.compile(pattern, re.IGNORECASE | re.UNICODE)
                for category, pattern in cls._CATEGORY_PATTERNS
            }
            cls._exclusion_compiled = re.compile(cls._EXCLUSION_PATTERN, re.IGNORECASE | re.UNICODE)
        return cls._compiled_patterns
    
    @classmethod
    def _get_exclusion_pattern(cls) -> Pattern:
        """Get compiled exclusion pattern."""
        if cls._exclusion_compiled is None:
            cls._get_compiled_patterns()  # This compiles both
        return cls._exclusion_compiled

    def categorize_narration(self):
        """Categorize transactions based on narration patterns.
    
        """
        if self.df.empty or 'narration' not in self.df.columns:
            return self.df

        self.df['category'] = 'others'
        narration = self.df['narration'].fillna('')  # Handle NaN values
        
        # Get pre-compiled patterns
        compiled_patterns = self._get_compiled_patterns()
        exclusion_pattern = self._get_exclusion_pattern()

        # Single pass through categories (instead of per-row iteration)
        for category, _ in self._CATEGORY_PATTERNS:
            pattern = compiled_patterns[category]
            
            # Only classify unclassified rows
            unclassified = self.df['category'] == 'others'
            
            # Use pre-compiled pattern for matching 
            mask = unclassified & narration.str.contains(pattern, regex=True).fillna(False)

            # Common exclusions
            if category in {
                'transfer', 'salary', 'loan_repayment',
                'loan_credit', 'betting', 'travelling', 'VAS'
            }:
                mask &= ~narration.str.contains(exclusion_pattern,regex=True).fillna(False)

            # Category-specific rules
            if category == 'loan_repayment':
                mask &= (self.df['type'] == 'debit') & (self.df['amount'] > 100)
        
            if category == 'salary':
                mask &= (self.df['type'] == 'credit') & (self.df['amount'] > 30_000)
            if category == 'VAS':
                mask &= (self.df['type'] == 'debit')

            if category == 'betting':
                mask &= (self.df['type'] == 'debit') & (self.df['amount'] > 100)

            if category == 'transfer':
                mask &= (self.df['amount'] > 100)

            elif category == 'loan_credit':
                mask &= (self.df['type'] == 'credit')
                category = 'loan'

            self.df.loc[mask, 'category'] = category

        return self.df

class ProcessorFactory:
    """Factory class for creating statement processors."""

    _processors: Dict[StatementType, Type[BaseStatementProcessor]] = {
        StatementType.MBS: MBSProcessor,
        StatementType.MONO: MonoProcessor,
        StatementType.GENERIC: GenericProcessor
    }

    @classmethod
    def register_processor(cls, statement_type: StatementType,
                           processor_class: Type[BaseStatementProcessor]):
        """Register a new statement processor class."""
        cls._processors[statement_type] = processor_class

    @classmethod
    def create_processor(cls, data: Dict[str, Any],
                         processor_type: Optional[StatementType] = None,
                         current_balance: float = None,
                         **kwargs
                         ) -> BaseStatementProcessor:
        """
        Create appropriate processor based on data format or explicit type.
        Auto-detection with fallback to generic processor.
        """

        if isinstance(data, dict):
            
            if 'Details' in data:
                return cls._processors[StatementType.MBS](data,current_balance=current_balance)
            elif 'result' in data:
                data = json.loads(data['result'])
                return cls._processors[StatementType.MBS](data,current_balance=current_balance)
            elif 'data' in data:
                return cls._processors[StatementType.MONO](data,current_balance=current_balance)

        return cls._processors[StatementType.GENERIC](data, current_balance=current_balance, **kwargs)

class DataExtractor(BaseDataTransformer):
    """Extracts and transforms bank statement data."""

    def __init__(self, json_data,current_balance: float = None):
        super().__init__()
        self.json_data = json_data
        self.current_balance = current_balance

    def transform_data(self, processor_type: Optional[StatementType] = None,
                       field_mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
        """Transform data using appropriate processor."""
        pd = _import_pandas()
        try:
            # Create processor using factory
            processor = ProcessorFactory.create_processor(
                self.json_data,
                processor_type,
                current_balance=self.current_balance,
                field_mapping=field_mapping
            )

            self.df = processor.process()

            if self.df.empty:
                return self.df
            
            # Apply categorization
            self.df = self.categorize_narration()

            # Include only needed fields
            include_cols = ['date', 'balance', 'amount', 'type', 'monthyear', 'weekno', 'category','narration']

            return self.df[include_cols].drop_duplicates()

        except Exception as e:
            print(f"Error processing data: {e}")
            pd = _import_pandas()
            return pd.DataFrame()