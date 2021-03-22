
# Import Libraries
import pandas as pd
import numpy as np
import glob
from os.path import abspath, dirname, join
from tika import parser
import matplotlib.pyplot as plt
from scipy.stats import linregress
import matplotlib.ticker as mtick

# Define list of month abbreviations
month_list = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Get list of all files in 'inputs' folder
file_list = glob.glob(abspath(join(dirname(__file__), "inputs\\*.pdf")))

# Function definitions
# Helper function to create date column
def build_date_string(df_row):
    return str(df_row['Year']) + '-' + str(df_row['Month']) + '-' + str(df_row['Day'])

# Helper function to futher categorize transactions
def categorize_txn(df_row):
    if df_row['AdditionalDescription'] in ['Osv-Payroll', 'Interac Corp.']:
        return 'Salary'
    elif df_row['Description'] == 'Credit memo':
        return 'Transfer from SA'
    elif df_row['DepositExpense'] == 'Expense' and df_row['AdditionalDescription'] in ['61762 00215 55', 'Inv 000000084296579']:
        return 'Transfer to Investment'
    elif df_row['DepositExpense'] == 'Deposit' and df_row['AdditionalDescription'] in ['61762 00215 55', 'Inv 000000084296579']:
        return 'Transfer from Investment'
    elif df_row['DepositExpense'] == 'Expense' and df_row['AdditionalDescription'] == 'Credit Card':
        return 'Credit Card Payment'
    elif (df_row['DepositExpense'] == 'Expense' 
          and df_row['Description'] == 'Debit memo' 
          and df_row['AdditionalDescription'] in ['Draft Purchase', 'Wire Payment']
          and df_row['Month'] in ['Apr', 'Jun']
          and df_row['Year'] == 2020):
        return 'House Downpayment'
    elif (df_row['DepositExpense'] == 'Expense' 
          and df_row['Description'] == 'Debit memo' 
          and df_row['AdditionalDescription'] == 'Draft Purchase'
          and df_row['Month'] == 'Jun'
          and df_row['Year'] == 2019):
        return 'Car Purchase'
    else:
        return f"Other {df_row['DepositExpense']}"

# Master function to read and parse transactions out of Scotia bank statement PDF documents
def parse_bank_statement_pdfs(file_list):
    # Initialize output list
    parsed_lst = []

    for file in file_list:
            
        year_changed = False
        print('Currently Processing {}'.format(file.split('\\')[-1]))
        # Parse out text from PDF document
        txt = parser.from_file(file)

        # Only keep PDF content
        txt = txt['content']

        # Split text by newline character
        split = txt.split('\n')

        # Loop through lines and verify that first three characters is a month abbreviation
        # Parse out relevant fields and append to dataframe
        # Initialize counter variable
        counter = 0
        line_counter = 0
        # Initialize year variable
        year = np.nan
        for line in split:
            line_counter += 1
            # Check if current line can assist in figuring out the statement year and assign to variable
            if 'Opening Balance on' in line:
                # Split line by space
                tmp_split = line.split(' ')
                year = int(tmp_split[-2])
            
            if line[:3] in month_list:
                # Split incoming string by space
                temp_split = line.split(' ')
                # Check if Amount and Balance fields can be parsed to float
                try:
                    float(temp_split[-2].replace(',', '')) and float(temp_split[-1].replace(',', ''))
                except:
                    # Check if current row depicts 'Opening Balance'
                    if temp_split[2] == 'Opening':
                        temp_dict = {'Month': temp_split[0],
                                     'Day': temp_split[1],
                                     'Year': year,
                                     'Description': 'Opening Balance',
                                     'AdditionalDescription': '',
                                     'Amount': 0,
                                     'Balance': temp_split[-1].replace(',', ''),
                                     'FileName': file.split('\\')[-1]}
                        parsed_lst.append(temp_dict)
                    continue
                # Check if Amount and Balance fields are in correct format, i.e. decimal point before two numbers
                if temp_split[-2][-3:-2] == '.' and temp_split[-1][-3:-2] == '.':
                    # Build transaction description
                    trans_desc = ''
                    txn_add_desc = ''
                    for line_split in temp_split:
                        
                        if line_split in [temp_split[0], temp_split[1], temp_split[-2], temp_split[-1]]:
                            continue
                        else:
                            trans_desc += ' ' + line_split
                            txn_add_desc = split[line_counter].strip()
                    
                    # Check if month changed from Dec to Jan since parsing previous transaction and increment year
                    if counter > 0:    
                        if temp_split[0] == 'Jan' and parsed_lst[counter]['Month'] == 'Dec' and year_changed == False and file.split('\\')[-1].split('_')[1] != '02':
                            year += 1
                            year_changed = True

                    temp_dict = {'Month': temp_split[0],
                                 'Day': temp_split[1],
                                 'Year': year,
                                 'Description': trans_desc.lstrip(),
                                 'AdditionalDescription': txn_add_desc,
                                 'Amount': temp_split[-2].replace(',', ''),
                                 'Balance': temp_split[-1].replace(',', ''),
                                 'FileName': file.split('\\')[-1]}
                    parsed_lst.append(temp_dict)
                    counter += 1

    # Parse result to dataframe
    parsed_df = pd.DataFrame(parsed_lst)

    # Parse Amount and Balance columns to float
    parsed_df['Amount'] = parsed_df['Amount'].astype(float)
    parsed_df['Balance'] = parsed_df['Balance'].astype(float)

    # Figure out if current transaction was a deposit or expense by checking whether Balance increased / decreased relative to previous transaction
    parsed_df['Change'] = parsed_df.Balance - parsed_df.Balance.shift(1)

    # If change is > 0 a deposit occurred, if change is < 0 assign expense label
    parsed_df['DepositExpense'] = parsed_df['Change'].apply(lambda x: 'Deposit' if x > 0 else 'Expense')

    # Create full date column and parse to pandas datetime
    parsed_df['Date'] = pd.to_datetime(parsed_df.apply(lambda x: build_date_string(x), axis=1))

    # Run txn categorization function
    parsed_df['TxnCategory'] = parsed_df.apply(lambda x: categorize_txn(x), axis=1)

    return parsed_df

# Call function to parse PDF documents
parsed_df = parse_bank_statement_pdfs(file_list)

# Define generalized function to produce plots
# Simply pass filtered dataframe
def produce_plot(filtered_df, plot_title, trend=False):
    # Copy incoming dataframe
    filtered_df_cpy = filtered_df.copy()
    # Determine ym from date
    filtered_df_cpy['ym'] = filtered_df_cpy['Date'].apply(lambda x: x.strftime('%Y%m'))
    # Sum Amount by ym
    pivot = pd.pivot_table(filtered_df_cpy, index='ym', values='Amount', aggfunc=np.sum).reset_index()
    pivot.columns = ['ym', 'Amount']

    fig, ax = plt.subplots()
    ax.tick_params(axis='x', rotation=45)
    ax.plot(pivot['ym'], pivot['Amount'], marker='o')

    ax.set(xlabel='Year Month', ylabel='Amount ($)',
        title=plot_title)
    fmt = '${x:,.0f}'
    tick = mtick.StrMethodFormatter(fmt)
    ax.yaxis.set_major_formatter(tick) 
    ax.grid()

    # Determine trendline if requested
    if trend:
        slope, intercept, r_value, p_value, std_err = linregress(pivot['ym'].astype(int), pivot['Amount'])
        ax.plot(pivot['ym'], intercept + slope*pivot['ym'].astype(int), '--r', label='fitted line')

    # Show plot
    plt.show()

# Generate line plot for credit card expenditures
filtered_df = parsed_df[parsed_df['TxnCategory'] == 'Credit Card Payment'].copy()
produce_plot(filtered_df, 'Credit Card', trend=True)

# Generate line plot for salary
filtered_df = parsed_df[parsed_df['TxnCategory'] == 'Salary'].copy()
produce_plot(filtered_df, 'Income', trend=True)

# Generate line plot for Toronto Hydro
filtered_df = parsed_df[parsed_df['AdditionalDescription'] == 'Toronto Hydro-Electric System'].copy()
produce_plot(filtered_df, 'Toronto Hydro', trend=True)

# Generate line plot for Enbridge Gas
filtered_df = parsed_df[parsed_df['AdditionalDescription'] == 'Enbridge Gas Inc'].copy()
produce_plot(filtered_df, 'Enbridge Gas', trend=True)

parsed_df.to_csv(abspath(join(dirname(__file__))) + '\outputs\parsed_df.csv', index=False)