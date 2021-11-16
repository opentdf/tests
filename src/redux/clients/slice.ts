import { createSlice } from "@reduxjs/toolkit";

export const clients = createSlice({
  name: 'clients',
  initialState: {},
  reducers: {
    getClients: (state) => state
  }
});

export const { getClients } = clients.actions;
export default clients.reducer;
