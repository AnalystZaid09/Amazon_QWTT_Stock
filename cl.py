import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Amazon QWTT Stock Report", layout="wide")

# Title and description
st.title("📊 Amazon QWTT Stock Report Generator")
st.markdown("Upload your inventory, business report, and product master files to generate a consolidated report")

# Create three columns for file uploads
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.subheader("📁 Inventory File")
    inventory_file = st.file_uploader("Upload Inventory CSV", type=['csv'], key='inventory')

with col2:
    st.subheader("📁 Business Report")
    business_file = st.file_uploader("Upload Business Report CSV", type=['csv'], key='business')

with col3:
    st.subheader("📁 Product Master")
    pm_file = st.file_uploader("Upload Product Master Excel", type=['xlsx', 'xls'], key='pm')
    
with col4:
    st.subheader("📁 QWTT Seller Flex Order")
    qwtt_file = st.file_uploader(
        "Upload QWTT Seller Flex CSV",
        type=['csv'],
        key='qwtt'
    )

# Process button
if st.button("🔄 Generate Report", type="primary", use_container_width=True):
    if not inventory_file or not business_file or not pm_file or not qwtt_file:
        st.error("⚠️ Please upload Inventory, Business Report, Product Master, and QWTT Seller Flex files")
    else:
        try:
            with st.spinner("Processing files..."):
                # Read files
                Inventory = pd.read_csv(inventory_file)
                Business_Report = pd.read_csv(business_file)
                PM = pd.read_excel(pm_file)
                QWTT = pd.read_csv(qwtt_file)
                
                
                # Normalize QWTT Status column
                status_col = next((c for c in QWTT.columns if 'status' in c.lower()), None)

                if status_col is None:
                    st.error("❌ Status column not found in QWTT file")
                    st.stop()

                QWTT[status_col] = QWTT[status_col].astype(str).str.strip().str.lower()

                # Remove cancelled and sidelined orders
                QWTT = QWTT[~QWTT[status_col].isin(['cancelled', 'sidelined'])]
                
                # Detect Order Value column
                order_value_col = next((c for c in QWTT.columns if 'order value' in c.lower()), None)

                if order_value_col is None:
                    st.error("❌ Order Value column not found in QWTT file")
                    st.stop()

                # Clean Order Value
                QWTT[order_value_col] = (
                    QWTT[order_value_col]
                        .astype(str)
                        .str.replace(r'[₹,$\s]', '', regex=True)
                        .replace('', '0')
                )

                QWTT[order_value_col] = pd.to_numeric(
                    QWTT[order_value_col], errors='coerce'
                ).fillna(0)

                # Remove zero-value orders
                QWTT = QWTT[QWTT[order_value_col] > 0]
                
                # Detect ASIN column in QWTT
                qwtt_asin_col = next((c for c in QWTT.columns if 'asin' in c.lower()), None)

                # Detect Units column in QWTT
                qwtt_units_col = next(
                    (c for c in QWTT.columns if 'unit' in c.lower() or 'quantity' in c.lower()),
                    None
                )

                if qwtt_asin_col is None or qwtt_units_col is None:
                    st.error(
                        f"❌ Couldn't detect ASIN or Units column in QWTT file "
                        f"(ASIN={qwtt_asin_col}, Units={qwtt_units_col})"
                    )
                    st.stop()
                    
                # Clean Units column
                QWTT[qwtt_units_col] = (
                    QWTT[qwtt_units_col]
                        .astype(str)
                        .str.replace(r'[,\s]', '', regex=True)
                        .replace('', '0')
                )

                QWTT[qwtt_units_col] = pd.to_numeric(
                    QWTT[qwtt_units_col], errors='coerce'
                ).fillna(0).astype(int)
                
                # QWTT Pivot Table (ASIN and Units)
                qwtt_pivot = pd.pivot_table(
                    QWTT,
                    index=qwtt_asin_col,
                    values=qwtt_units_col,
                    aggfunc='sum',
                    margins=True,
                    margins_name='Grand Total'
                )
                
                qwtt_pivot = qwtt_pivot.rename(columns={qwtt_units_col: 'QWTT Units'})

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
                # Find CP column in Purchase Master
                pm_cp = next((c for c in PM.columns if c.lower() == "cp"), None)

                if pm_cp is None:
                    st.error("❌ CP column not found in Purchase Master")
                    st.stop()

                # Create PM mappings
                map_manager = PM.set_index(pm_asin)[pm_manager].to_dict()
                map_brand = PM.set_index(pm_asin)[pm_brand].to_dict()
                map_product = PM.set_index(pm_asin)[pm_product].to_dict()
                map_vendor = PM.set_index(pm_asin)[pm_vendor].to_dict()
                map_cp = PM.set_index(pm_asin)[pm_cp].to_dict()

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
                
                inv_pivot = pivot_Inv.copy()
                inv_pivot = inv_pivot.reset_index()
                inv_pivot.rename(columns={
                    "Asin": "ASIN",
                    "Sellable": "Current Stock"
                }, inplace=True)

                inv_pivot = inv_pivot[inv_pivot["ASIN"] != "Grand Total"]
                
                inv_pivot["Brand"] = inv_pivot["ASIN"].map(map_brand)
                inv_pivot["Brand Manager"] = inv_pivot["ASIN"].map(map_manager)
                inv_pivot["Product Name"] = inv_pivot["ASIN"].map(map_product)
                inv_pivot["Vendor SKU"] = inv_pivot["ASIN"].map(map_vendor)
                inv_pivot["CP"] = inv_pivot["ASIN"].map(map_cp)
                
                qwtt_sales_map = (
                    qwtt_pivot
                    .reset_index()
                    .rename(columns={qwtt_asin_col: "ASIN", "QWTT Units": "Sales Units/Qty"})
                )

                qwtt_sales_map = qwtt_sales_map[qwtt_sales_map["ASIN"] != "Grand Total"]

                sales_qty_map = dict(
                    zip(qwtt_sales_map["ASIN"].astype(str), qwtt_sales_map["Sales Units/Qty"])
                )

                inv_pivot["Sales Units/Qty"] = (
                    inv_pivot["ASIN"].astype(str)
                    .map(sales_qty_map)
                    .fillna(0)
                    .astype(int)
                )
                
                inv_pivot["CP"] = pd.to_numeric(inv_pivot["CP"], errors="coerce").fillna(0)
                inv_pivot["As per Qty CP"] = inv_pivot["CP"] * inv_pivot["Current Stock"]
                
                # ==============================
                # QWTT SALES REPORT (NEW REPORT)
                # ==============================

                qwtt_sales_report = inv_pivot[
                    [
                        "ASIN",
                        "Brand",
                        "Brand Manager",
                        "Product Name",
                        "Vendor SKU",
                        "Current Stock",
                        "Sales Units/Qty",
                        "CP",
                        "As per Qty CP"
                    ]
                ]
                
                # =========================
                # ADD GRAND TOTAL ROW
                # =========================

                total_stock = qwtt_sales_report["Current Stock"].sum()
                total_cp_value = qwtt_sales_report["As per Qty CP"].sum()

                weighted_cp = (
                    total_cp_value / total_stock if total_stock > 0 else 0
                )

                grand_total_row = {
                    "ASIN": "Grand Total",
                    "Brand": "",
                    "Brand Manager": "",
                    "Product Name": "",
                    "Vendor SKU": "",
                    "Current Stock": total_stock,
                    "Sales Units/Qty": qwtt_sales_report["Sales Units/Qty"].sum(),
                    "CP": round(weighted_cp, 2),
                    "As per Qty CP": total_cp_value,
                }

                qwtt_sales_report = pd.concat(
                    [qwtt_sales_report, pd.DataFrame([grand_total_row])],
                    ignore_index=True
                )

                # Store in session state
                st.session_state['result'] = pivot_final
                
                st.session_state["qwtt_sales_report"] = qwtt_sales_report

                st.success("✅ Report generated successfully!")

        except Exception as e:
            st.error(f"❌ Error processing files: {str(e)}")
            st.exception(e)

# Display results if available
if 'result' in st.session_state:
    st.markdown("---")

    tab1, tab2 = st.tabs(
        ["📦 Inventory / Stock Report", "📊 QWTT Sales Report"]
    )

    # =========================
    # TAB 1: INVENTORY REPORT
    # =========================
    with tab1:
        st.subheader("📦 Inventory / Stock Report")

        result = st.session_state['result']

        col1, col2, col3, col4 = st.columns(4)

        product_count = (
            len(result) - 1 if "Grand Total" in result['Asin'].values else len(result)
        )
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
                "Sales QTY": st.column_config.NumberColumn("Sales QTY", format="%d"),
            },
        )

        csv1 = result.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Inventory / Stock Report",
            data=csv1,
            file_name="inventory_stock_report.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

    # =========================
    # TAB 2: QWTT SALES REPORT
    # =========================
    with tab2:
        st.subheader("📊 QWTT Sales Report")

        qwtt_sales_report = st.session_state["qwtt_sales_report"]

        st.dataframe(
            qwtt_sales_report,
            use_container_width=True,
            height=500,
        )

        csv2 = qwtt_sales_report.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download QWTT Sales Report",
            data=csv2,
            file_name="qwtt_sales_report.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

# Footer (UNCHANGED)
st.markdown("---")
st.markdown(
    "💡 **Tip**: Make sure your files have the correct column names: "
    "`Asin`, `Sellable` in Inventory, and matching ASIN columns in all files."
)
