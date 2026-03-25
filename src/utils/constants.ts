export const CUSTOMER_TYPES = {
  RETAILER: 'Retailer',
  FINAL_CLIENT: 'Final Client',
  DESIGNER: 'Designer',
  WHOLESALER: 'Wholesaler',
  OTHER: 'Other',
} as const;

export type CustomerType = typeof CUSTOMER_TYPES[keyof typeof CUSTOMER_TYPES];
