import openpyxl

class _RowWrapper:
    def __init__(self, data):
        self.data = data
    def __iter__(self):
        return iter(self.data)
    def __len__(self):
        return len(self.data)
    def __getitem__(self, idx):
        return self.data[idx]
    @property
    def values(self):
        return self.data
    @property
    def iloc(self):
        return self

class _ILocWrapper:
    def __init__(self, data):
        self.data = data
    def __getitem__(self, idx):
        if isinstance(idx, tuple):
            row_idx, col_idx = idx
            row = self.data[row_idx]
            if col_idx < len(row):
                return row[col_idx]
            return ""
        return _RowWrapper(self.data[idx])

class MockDataFrame:
    def __init__(self, data):
        self.data = data
        self.iloc = _ILocWrapper(data)
        self.columns = data[0] if data else []
        
    def __len__(self):
        return len(self.data)
        
    def fillna(self, value):
        new_data = []
        for row in self.data:
            new_row = []
            for v in row:
                if v is None:
                    new_row.append(value)
                elif str(v).lower() == 'nan':
                    new_row.append(value)
                else:
                    new_row.append(str(v))
            new_data.append(new_row)
        return MockDataFrame(new_data)

def read_excel(file_object, header=None, dtype=str):
    wb = openpyxl.load_workbook(file_object, data_only=True)
    ws = wb.active
    data = []
    max_col = 0
    # First pass to find max columns
    for row in ws.iter_rows(values_only=True):
        if len(row) > max_col:
            max_col = len(row)
            
    # Second pass to normalize rows
    for row in ws.iter_rows(values_only=True):
        row_list = list(row)
        while len(row_list) < max_col:
            row_list.append(None)
        data.append(row_list)
        
    return MockDataFrame(data)

class pd:
    @staticmethod
    def read_excel(file_object, header=None, dtype=str):
        return read_excel(file_object, header=header, dtype=dtype)
