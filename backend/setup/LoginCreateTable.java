package com.amazonaws.samples;

import java.util.Arrays;

import com.amazonaws.auth.profile.ProfileCredentialsProvider;
import com.amazonaws.regions.Regions;
import com.amazonaws.services.dynamodbv2.AmazonDynamoDB;
import com.amazonaws.services.dynamodbv2.AmazonDynamoDBClientBuilder;
import com.amazonaws.services.dynamodbv2.document.DynamoDB;
import com.amazonaws.services.dynamodbv2.document.Table;
import com.amazonaws.services.dynamodbv2.model.AttributeDefinition;
import com.amazonaws.services.dynamodbv2.model.KeySchemaElement;
import com.amazonaws.services.dynamodbv2.model.KeyType;
import com.amazonaws.services.dynamodbv2.model.ProvisionedThroughput;
import com.amazonaws.services.dynamodbv2.model.ScalarAttributeType;

public class LoginCreateTable {

    public static void main(String[] args) throws Exception {

        // Create DynamoDB client
        AmazonDynamoDB client = AmazonDynamoDBClientBuilder.standard().withRegion(Regions.AP_SOUTHEAST_2).withCredentials().build();

        DynamoDB dynamoDB = new DynamoDB(client);

        String tableName = "Login";

        try {
            System.out.println("Attempting to create Login table; please wait...");

            Table table = dynamoDB.createTable(tableName,

                    // Primary Key (Partition Key only)
                    Arrays.asList(
                            new KeySchemaElement("email", KeyType.HASH)
                    ),

                    // Attribute Definitions
                    Arrays.asList(
                            new AttributeDefinition("email", ScalarAttributeType.S)
                    ),

                    // Throughput (can adjust if needed)
                    .withBillingMode(BillingMode.PAY_PER_REQUEST)
            );

            table.waitForActive();

            System.out.println("Success! Table created.");
            System.out.println("Table Status: " + table.getDescription().getTableStatus());

        } catch (Exception e) {
            System.err.println("Unable to create table:");
            System.err.println(e.getMessage());
        }
    }
}