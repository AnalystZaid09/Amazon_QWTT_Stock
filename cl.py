import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Amazon QWTT Stock Report", layout="wide")

# Title and description
st.title("📊 Amazon QWTT Stock Report Generator")
st.markdown("Upload your inventory, business report, and product master files to generate a consolidated report")

# Create three columns for file uploads
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("📁 Inventory File")
    inventory_file = st.file_uploader("Upload Inventory CSV", type=['csv'], key='inventory')

with col2:
    st.subheader("📁 Business Report")
    business_file = st.file_uploader("Upload Business Report CSV", type=['csv'], key='business')

with col3:
    st.subheader("📁 Product Master")
    pm_file = st.file_uploader("Upload Product Master Excel", type=['xlsx', 'xls'], key='pm')

# Process button
if st.button("🔄 Generate Report", type="primary", use_container_width=True):
    if not inventory_file or not business_file or not pm_file:
        st.error("⚠️ Please upload all three files before generating the report")
    else:
        try:
            with st.spinner("Processing files..."):
                # Read files
                Inventory = pd.read_csv(inventory_file)
                Business_Report = pd.read_csv(business_file)
                PM = pd.read_excel(pm_file)

                # Create pivot table from inventory
                pivot_Inv = pd.pivot_table(
                    Inventory,
                    index="Asin",
                    values="Sellable",
                    aggfunc="sum",
                    margins=True,
                    margins_name="Grand Total"
                )

                # Find business report columns (case-insensitive)
                biz_asin_col = next((c for c in Business_Report.columns if 'asin' in c.lower()), None)
                biz_totitems_col = next((c for c in Business_Report.columns
                                       if 'total order items' in c.lower() or 'order items' in c.lower()), None)

                if biz_asin_col is None or biz_totitems_col is None:
                    st.error(f"Couldn't detect required columns in Business Report. Found: ASIN={biz_asin_col}, Total Items={biz_totitems_col}")
                    st.stop()

                # Clean business report data
                biz = Business_Report.copy()
                biz[biz_totitems_col] = (
                    biz[biz_totitems_col].astype(str)
                       .str.replace(r'[,₹\$\s]', '', regex=True)
                       .replace('', '0')
                )
                biz[biz_totitems_col] = pd.to_numeric(biz[biz_totitems_col], errors='coerce').fillna(0).astype(int)

                # Create sales mapping
                mapping = {str(k).strip(): int(v) for k, v in biz.set_index(biz_asin_col)[biz_totitems_col].to_dict().items()}

                # Add sales quantity to pivot
                pivot = pivot_Inv.copy()
                pivot['Sales QTY'] = pivot.index.to_series().astype(str).str.strip().map(mapping).fillna(0).astype(int)

                # Update Grand Total for Sales QTY
                if "Grand Total" in pivot.index:
                    pivot.at["Grand Total", "Sales QTY"] = int(pivot.loc[pivot.index != "Grand Total", "Sales QTY"].sum())

                # Sort by Sales QTY
                if "Grand Total" in pivot.index:
                    grand_total_row = pivot.loc[["Grand Total"]]
                    pivot_no_total = pivot.drop(index="Grand Total")
                else:
                    pivot_no_total = pivot

                pivot_sorted = pivot_no_total.sort_values(by="Sales QTY", ascending=True)

                # Add Grand Total back
                if "Grand Total" in pivot_Inv.index:
                    pivot_sorted = pd.concat([pivot_sorted, grand_total_row])

                # Reset index to make Asin a column
                pivot_sorted = pivot_sorted.reset_index()
                pivot_sorted.rename(columns={"index": "Asin", "Sellable": "Stock"}, inplace=True)

                # Find PM columns
                pm_asin = next(c for c in PM.columns if "asin" in c.lower())
                pm_manager = next(c for c in PM.columns if "manager" in c.lower())
                pm_brand = next(c for c in PM.columns if c.lower() == "brand")
                pm_product = next(c for c in PM.columns if "product" in c.lower() and "name" in c.lower())
                pm_vendor = next(c for c in PM.columns if "vendor" in c.lower() and "sku" in c.lower())

                # Create PM mappings
                map_manager = PM.set_index(pm_asin)[pm_manager].to_dict()
                map_brand = PM.set_index(pm_asin)[pm_brand].to_dict()
                map_product = PM.set_index(pm_asin)[pm_product].to_dict()
                map_vendor = PM.set_index(pm_asin)[pm_vendor].to_dict()

                # Add PM data to pivot
                pivot_sorted["Manager"] = pivot_sorted["Asin"].astype(str).str.strip().map(map_manager)
                pivot_sorted["Brand"] = pivot_sorted["Asin"].astype(str).str.strip().map(map_brand)
                pivot_sorted["Product Name"] = pivot_sorted["Asin"].astype(str).str.strip().map(map_product)
                pivot_sorted["Vendor SKU"] = pivot_sorted["Asin"].astype(str).str.strip().map(map_vendor)

                # Convert all object columns to string to avoid Arrow serialization issues
                for col in ["Manager", "Brand", "Product Name", "Vendor SKU"]:
                    pivot_sorted[col] = pivot_sorted[col].astype(str).replace('nan', '')

                # Reorder columns
                final_cols = ["Asin", "Manager", "Brand", "Product Name", "Vendor SKU", "Stock", "Sales QTY"]
                pivot_final = pivot_sorted[final_cols]

                # Store in session state
                st.session_state['result'] = pivot_final

                st.success("✅ Report generated successfully!")

        except Exception as e:
            st.error(f"❌ Error processing files: {str(e)}")
            st.exception(e)

# Display results if available
if 'result' in st.session_state:
    st.markdown("---")
    st.subheader("📈 Generated Report")
    
    result = st.session_state['result']
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    # Exclude Grand Total from product count
    product_count = len(result) - 1 if "Grand Total" in result['Asin'].values else len(result)
    total_stock = result[result['Asin'] != 'Grand Total']['Stock'].sum()
    total_sales = result[result['Asin'] != 'Grand Total']['Sales QTY'].sum()
    
    with col1:
        st.metric("Total Products", f"{product_count:,}")
    with col2:
        st.metric("Total Stock", f"{total_stock:,}")
    with col3:
        st.metric("Total Sales QTY", f"{total_sales:,}")
    with col4:
        sell_through = (total_sales / total_stock * 100) if total_stock > 0 else 0
        st.metric("Sell-through Rate", f"{sell_through:.1f}%")
    
    # Display dataframe
    st.dataframe(
        result,
        use_container_width=True,
        height=500,
        column_config={
            "Asin": st.column_config.TextColumn("ASIN", width="small"),
            "Manager": st.column_config.TextColumn("Manager", width="small"),
            "Brand": st.column_config.TextColumn("Brand", width="small"),
            "Product Name": st.column_config.TextColumn("Product Name", width="large"),
            "Vendor SKU": st.column_config.TextColumn("Vendor SKU", width="small"),
            "Stock": st.column_config.NumberColumn("Stock", format="%d"),
            "Sales QTY": st.column_config.NumberColumn("Sales QTY", format="%d")
        }
    )
    
    # Download button
    csv = result.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Report as CSV",
        data=csv,
        file_name="inventory_sales_report.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True
    )

# Footer
st.markdown("---")
st.markdown("💡 **Tip**: Make sure your files have the correct column names: `Asin`, `Sellable` in Inventory, and matching ASIN columns in all files.")